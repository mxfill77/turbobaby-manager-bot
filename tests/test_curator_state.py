"""КУРАТОР СПРАШИВАЕТ ПРИБОР, ПРЕЖДЕ ЧЕМ ВЫПИСАТЬ ПУНКТ ВЛАДЕЛЬЦУ (11.08.2026).

ПОВОД — четыре живых случая подряд: конверт 437 просил «да» на перезапуск splinter, сделанный
задачей 438 за 11 минут ДО нажатия; карточка 460 просила рестарт демона через час после того, как
О3 объявило расхождение диска; карточка 463 просила удаление рабочего дерева без слова о его
содержимом; карточка 429 — заливку из папки, которая стёрла бы прод. Общее: куратор пишет о МИРЕ,
ни разу его не спросив (он читает отчёт задачи, а отчёт стареет с минуты написания).

ЗАМЕР (снимок очереди 11.08.2026, 475 строк; журнал systemd; классификатор боевой): пунктов
ветки human, дошедших до владельца, — 33 (карточек `[куратор владельцу цель N]` в очереди 35);
операцию, наблюдаемую прибором, назвали 18; коммит + операцию — 13. К моменту ПОКАЗА пункта
операция уже была состоявшейся у ОДНОГО (карточка 347: коммит 4a7ef75 в 13:35:33, демон поднят в
13:39:37, пункт выписан в 13:42:39 — на три минуты позже доставки). Пока карточка ВИСЕЛА, операция
успевала состояться ещё у трёх (106, 202, 437) — это соседнее окно, оно здесь НЕ закрывается и
названо в остатках.

ЧТО ЗАКРЕПЛЕНО:
  пункт, чью операцию прибор О3 нашёл УЖЕ состоявшейся, закрывается сам — карточки владельцу нет
  вовсе, след остаётся в журнале демона и в карточке-отчёте 328;
  ВСЁ ОСТАЛЬНОЕ — вопрос владельцу, как раньше, БАЙТ-В-БАЙТ. «Состоялось» возвращается ровно
  одним путём; дырка в фактах, молчание прибора, незасчитанная операция, сбой git, мёртвый
  процесс, упавший разбор — всё это вопрос, а не тишина.

ПРИЗНАК ОДИН И НЕ ЯВЛЯЕТСЯ ПЕРЕЧНЕМ ВИДОВ (иначе он протух бы на первом новом виде пункта):
операция засчитана, только если её НАЗВАЛ САМ ПРИБОР в ответе о доставке. Поэтому выкладка моста,
живые таблицы, файл секретов и удаление файлов не могут быть засчитаны ФИЗИЧЕСКИ — не списком, а
тем, что в ответе прибора таких семей не бывает.

ЖИВОЙ ФОРМАТ (класс row705→1268): тексты пунктов — ДОСЛОВНО из карточек 347, 436, 459, 428, 462,
250, 122 (снимок очереди 11.08.2026); факты доставки — той же формы, что собирает рука наблюдателя
(замыкания импортов, /proc, mtime, окно origin/main); судит их боевой `expectations.delivery_state`.

Проверки:
 (1) чистое решение: единственный импорт, три исхода, «состоялось» только по положительному пути;
 (2) СОСТОЯВШЕЕСЯ НЕ СПРАШИВАЕТ: карточка 347 дословно → пункт закрыт, обращений к мосту НОЛЬ;
 (3) НЕИЗВЕСТНОЕ СПРАШИВАЕТ: 436/459/428/462/250/122 дословно → карточка владельцу, как раньше;
 (4) ЗАМОК по каждой дырке отдельно: дерево не сверено · процесс не наблюдается · коммит вне окна
     · доставка засчитана ДРУГОЙ двери · разбор упал → пункт выписывается;
 (5) ОТКАТ CURATOR_STATE=0: путь байт-в-байт прежний и НИ ОДНОГО обращения к фактам;
 (6) ГРАНИЦЫ: развод по операциям и общая карточка не тронуты; отчёт 328 несёт закрытие без
     маркера «⚠️» (иначе devbot перестал бы вклеивать вердикт строкой); файл счёта серии не тронут;
 (7) страж чистоты CURATOR_STATE_PURE краснеет на модуле с руками.
"""
import datetime
import hashlib
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"    # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "1"
os.environ["CURATOR_SCOPE"] = "0"
os.environ["CURATOR_STATE"] = "1"

REPO = "/root/turbobaby-manager-bot"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

import curator_state                     # noqa: E402
import expectations                      # noqa: E402
import scan_result                       # noqa: E402
import orchestrator_daemon as OD         # noqa: E402

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# ── ЖИВОЙ ФОРМАТ: пункты боевых карточек ДОСЛОВНО (снимок очереди 11.08.2026) ────────────────
CARD347 = (
    "Шаг 1 цели 344 вернул отчёт без факта — ни MainPID, ни ActiveEnterTimestamp, ни имени "
    "единицы: живёт ли в проде фикс 4a7ef75 (curator_event.py), неизвестно, а повторную проверку "
    "по смыслу дублирует уже отработавшая задача 346; нужно твоё «да» на отложенный рестарт "
    "демона `systemd-run --on-active=10s systemctl restart orchestrator-daemon` (правило "
    "самомодификации, splinter не трогаем), после которого исполнитель назовёт единицу, PID и "
    "время старта и запишет строку в cc_log.")
CARD436 = (
    "Нужно твоё «да» на рестарт splinter: фикс скана просрочек (коммит 6e525d6) лежит в "
    "origin/main и гейт зелёный, но живой процесс держит старый код и считает по-старому — "
    "исходное ТЗ рестарт запрещало намеренно, поэтому сам не делаю.")
CARD459 = (
    "Нужно твоё «да» на отложенный рестарт orchestrator-daemon (`systemd-run --on-active=10s "
    "systemctl restart orchestrator-daemon`): счёт серии живёт в памяти демона, задание рестарт "
    "прямо запретило — до него ветка chain_series в проде не работает (файл нулевой, сверка "
    "отвечает «сверять нечего»). После рестарта — прогон сверки для контроля.")
CARD428 = (
    "Нужно твоё «да» на выкат моста (`clasp push` + `clasp redeploy` прод-деплоя из "
    "/root/turbobaby-bridge-gs): правки ReadFleet/Bridge под контракт трёх состояний живут только "
    "в папке — прод-мост о них не знает, и python-сторона (коммит 51c44cd) в проде работает "
    "против старого моста; папка не под git, работа ничем не защищена. Перед push обязателен "
    "отпечаток прода (HEAD может быть впереди чужой работой).")
CARD462 = (
    "Убрать оставшееся в корне репо рабочее дерево пробы `_scratch_series_iso_0810/` (worktree на "
    "5629a6c) — это удаление вне временных каталогов, красная зона; нужно твоё «да» (правило R17: "
    "scratch в корне невидим для git status)")
CARD250 = (
    "Нужен владелец на красное: (1) деплой моста — `clasp push` + `clasp redeploy` "
    "прод-deploymentId (до него edit_event в проде отвечает unknown_action, эффект кода живым "
    "фактом НЕ доказан — FACT-блока в итоге нет); (2) после деплоя на живом случае NMAX 155 "
    "GREEN-B 4957 — правка строки событий 29.07 09:32:15 (38982→36982) и понижение Лист1 I16 "
    "37000→36982 веткой «исправление ошибки», каждое по отдельному «да» с карточкой и откатом.")
CARD122 = (
    "Одобрение на карточке 110 (11:41:41) съедено старым кодом демона и НЕ исполнено — подтверди "
    "её заново (или скажи, что она неактуальна): цель рестарта достигнута, демон PID 267939 уже "
    "крутит fc07efa, но потерянное «да» по 110 машина восстановить не может.")

DAEMON_ENTRY = "orchestrator_daemon.py"
SPLINTER_ENTRY = "bot.py"


class Facts:
    """Факты доставки ТОЙ ЖЕ ФОРМЫ, что собирает рука наблюдателя, + счётчик обращений.

    Замыкания и живые процессы подменяются целиком — иначе тест мерил бы состояние ЭТОЙ машины
    (какой юнит сейчас поднят), а не правило. Файлы коммита — настоящие файлы репозитория:
    свидетель по mtime обязан работать на живом формате, а не на выдуманном пути."""

    def __init__(s, files, ct_shift=-600.0, started_after=True, unit="orchestrator-daemon",
                 dirty=(), dirty_ok=True, alive=True, in_window=True):
        s.files, s.unit = list(files), unit
        s.dirty, s.dirty_ok, s.alive, s.in_window = list(dirty), dirty_ok, alive, in_window
        s.calls = {"commits": 0, "closure": 0, "live": 0, "dirty": 0}
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        s.ct = now + ct_shift
        mts = [os.stat(os.path.join(REPO, f)).st_mtime
               for f in s.files if os.path.exists(os.path.join(REPO, f))]
        edge = max([s.ct] + mts)
        s.started = (edge + 60.0) if started_after else (min([s.ct] + mts) - 60.0)

    def commits_since(s, ts, repo=None):
        s.calls["commits"] += 1
        if not s.in_window:
            return []
        return [{"sha": "4a7ef75", "ct": int(s.ct), "subject": "фикстура", "files": s.files}]

    def closure(s, entry, repo=None):
        s.calls["closure"] += 1
        return set([entry] + s.files) if entry == _entry_of(s.unit) else {entry}

    def live(s, unit, entry, proc=None, repo=None):
        s.calls["live"] += 1
        if not s.alive:
            return None
        return {"pid": 1234, "started": s.started}

    def dirty_files(s):
        """ЖИВОЙ ФОРМАТ контракта читателя: «дерево чистое» и «спросить не удалось» — разные
        исходы, и подмена обязана уметь оба, иначе замок не проверен."""
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
    return DAEMON_ENTRY


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
    """Очередь в памяти (образец test_curator_split.FakeBridge) + счётчик ЛЮБОГО обращения."""

    def __init__(s):
        s.rows, s.nid, s.calls = {}, 700, []

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


def place(item, facts=None, root=344):
    """Пункт → (id карточки | None, режим, примечание) через БОЕВОЙ вход ветки human."""
    fb = FakeBridge()
    keep = OD.bc
    OD.bc = fb
    try:
        if facts is None:
            r = OD._curator_human_place(root, item)
        else:
            r = with_facts(facts, OD._curator_human_place, root, item)
    finally:
        OD.bc = keep
    return r, fb


# ══════════════ (1) ЧИСТОЕ РЕШЕНИЕ ══════════════════════════════════════════════════════════
print("\n(1) чистое решение: инструментов нет, исходов три")
src = open(os.path.join(REPO, "curator_state.py"), encoding="utf-8").read()
imports = [l for l in src.splitlines() if l.startswith(("import ", "from "))]
res.append(ok(imports == ["import re"], "импорт ровно один (`re`): спросить мир решению нечем"))
res.append(ok(len({curator_state.SETTLED, curator_state.OPEN, curator_state.UNSEEN}) == 3,
              "исходов три, и «неизвестно» — отдельное слово, а не вежливое «состоялось»"))
res.append(ok(curator_state.shas(CARD347) == ["4a7ef75"]
              and curator_state.shas(CARD436) == ["6e525d6"]
              and curator_state.shas(CARD459) == [],
              "коммиты пункта разбираются дословно (347→4a7ef75, 436→6e525d6, 459→нет)"))

A_OK = {"4a7ef75": {"ok": True, "state": expectations.DELIVERED,
                    "families": ["service:orchestrator-daemon"]}}
res.append(ok(curator_state.verdict(["service:orchestrator-daemon"], A_OK)["state"]
              == curator_state.SETTLED, "прибор подтвердил коммит И операцию → «состоялось»"))
res.append(ok(curator_state.verdict([], A_OK)["state"] == curator_state.UNSEEN,
              "операции не названо → «неизвестно» (подтверждать нечего)"))
res.append(ok(curator_state.verdict(["service:orchestrator-daemon"], {})["state"]
              == curator_state.UNSEEN, "коммита не названо → «неизвестно» (опоры нет)"))
res.append(ok(curator_state.verdict(["service:splinter"], A_OK)["state"] == curator_state.UNSEEN,
              "доставка засчитана ДРУГОЙ двери → «неизвестно», а не «состоялось»"))
res.append(ok(curator_state.verdict(
    ["service:orchestrator-daemon"],
    {"4a7ef75": {"ok": False, "state": expectations.UNDELIVERED, "families": []}}
)["state"] == curator_state.OPEN, "прибор доказал обратное → «не состоялось» (вопрос настоящий)"))
res.append(ok(curator_state.verdict(
    ["service:orchestrator-daemon"],
    {"4a7ef75": {"ok": None, "state": expectations.UNKNOWN, "families": []}}
)["state"] == curator_state.UNSEEN, "прибор ответил «неизвестно» → пункт не закрывается"))
res.append(ok(curator_state.verdict(
    ["service:orchestrator-daemon"],
    {"4a7ef75": {"ok": True, "state": expectations.DELIVERED,
                 "families": ["service:orchestrator-daemon"]},
     "51c44cd": {"ok": False, "state": expectations.UNDELIVERED, "families": []}}
)["state"] == curator_state.OPEN,
    "порядок силы прибора: один недоставленный коммит бьёт доставку остальных"))

# ══════════════ (2) СОСТОЯВШЕЕСЯ НЕ СПРАШИВАЕТ ══════════════════════════════════════════════
print("\n(2) состоявшееся не спрашивает: карточка 347 ДОСЛОВНО")
f = Facts(["curator_event.py"], started_after=True, unit="orchestrator-daemon")
r, fb = place(CARD347, f)
res.append(ok(r is not None and r[1] == "settled", "пункт 347 закрыт сверкой (режим «settled»)"))
res.append(ok(r is not None and r[0] is None, "id карточки владельцу нет — её не создавали"))
res.append(ok(fb.calls == [], "обращений к мосту НОЛЬ: владельцу не показано вовсе (%s)" % fb.calls))
res.append(ok(r is not None and "4a7ef75" in r[2] and "service:orchestrator-daemon" in r[2],
              "обоснование называет коммит и операцию, которые подтвердил прибор"))
res.append(ok(f.calls["dirty"] == 1 and f.calls["live"] >= 1,
              "замок про дерево и живой процесс спрошен по-настоящему (git+/proc)"))

# ══════════════ (3) НЕИЗВЕСТНОЕ СПРАШИВАЕТ ══════════════════════════════════════════════════
print("\n(3) неизвестное спрашивает: пункты владельцу доезжают, как раньше")
CASES = (
    ("436 (процесс стартовал ДО коммита)", CARD436,
     Facts(["splinter.py"], started_after=False, unit="splinter")),
    ("459 (коммита в пункте не названо)", CARD459, Facts(["chain_series.py"])),
    ("428 (выкладка моста прибором не наблюдается)", CARD428, Facts(["bridge_client.py"])),
    ("462 (операции не названо — просит решение)", CARD462, Facts(["chain_series.py"])),
    ("250 (живые таблицы + выкладка моста)", CARD250, Facts(["bridge_client.py"])),
    ("122 (пункт просит подтвердить съеденное «да»)", CARD122, Facts(["orchestrator_daemon.py"])),
)
for name, text, facts in CASES:
    r, fb = place(text, facts)
    good = r is not None and r[1] != "settled" and "enqueue_task" in fb.calls
    res.append(ok(good, "%s → карточка владельцу создана (%s)" % (name, r and r[1])))

# ══════════════ (4) ЗАМОК: КАЖДАЯ ДЫРКА — ВОПРОС, А НЕ ТИШИНА ═══════════════════════════════
print("\n(4) замок: проверить не смогли → пункт выписывается")
HOLES = (
    ("дерево с origin/main не сверено", Facts(["curator_event.py"], dirty_ok=False)),
    ("файл коммита разошёлся с origin", Facts(["curator_event.py"], dirty=["curator_event.py"])),
    ("процесс не наблюдается", Facts(["curator_event.py"], alive=False)),
    ("коммит вне окна прибора", Facts(["curator_event.py"], in_window=False)),
    ("доставка засчитана другой двери", Facts(["curator_event.py"], unit="splinter")),
)
for name, facts in HOLES:
    r, fb = place(CARD347, facts)
    res.append(ok(r is not None and r[1] != "settled" and "enqueue_task" in fb.calls,
                  "%s → карточка владельцу есть (режим %s)" % (name, r and r[1])))


class Boom:
    """Сбор фактов падает — правило обязано отдать пункт владельцу, а не проглотить его."""
    calls = {"dirty": 0}

    def commits_since(s, ts, repo=None):
        raise RuntimeError("git недоступен")

    def closure(s, entry, repo=None):
        return {entry}

    def live(s, unit, entry, proc=None, repo=None):
        return None

    def dirty_files(s):
        return scan_result.ScanResult(scanned=0, parsed=0,
                                      subject="файлов расхождения с origin/main", payload=[])


r, fb = place(CARD347, Boom())
res.append(ok(r is not None and r[1] != "settled" and "enqueue_task" in fb.calls,
              "сбор фактов упал → карточка владельцу есть (fail-safe в сторону вопроса)"))

# ══════════════ (5) ОТКАТ ═══════════════════════════════════════════════════════════════════
print("\n(5) откат CURATOR_STATE=0: путь прежний и фактов не спрашивают")
os.environ["CURATOR_STATE"] = "0"
f_off = Facts(["curator_event.py"], started_after=True, unit="orchestrator-daemon")
r_off, fb_off = place(CARD347, f_off)
os.environ["CURATOR_STATE"] = "1"
res.append(ok(r_off is not None and r_off[1] == "created" and "enqueue_task" in fb_off.calls,
              "при выключенной сверке пункт 347 идёт владельцу прежним путём"))
res.append(ok(f_off.calls == {"commits": 0, "closure": 0, "live": 0, "dirty": 0},
              "ветка мертва ДО чтения фактов: ни git, ни /proc (%s)" % f_off.calls))
r_on, _ = place(CARD347, Facts(["curator_event.py"], started_after=True))
res.append(ok(r_on[1] == "settled" and r_off[1] == "created",
              "один и тот же пункт: с флагом закрыт, без флага выписан — разница только в флаге"))

# ══════════════ (6) ГРАНИЦЫ ═════════════════════════════════════════════════════════════════
print("\n(6) границы: соседние правила и каналы не тронуты")
card = OD._curator_card_text("задача", 346, {"verdict": "human", "human": CARD347,
                                             "reason": "нужен владелец"},
                             None, (None, "settled", "прибор подтвердил: 4a7ef75 уже в проде"))
res.append(ok("НЕ создавалась" in card and "🔍" in card,
              "отчёт 328 прямо говорит, что карточки владельцу не было"))
res.append(ok("⚠️" not in card,
              "закрытие НЕ метится «⚠️» — иначе devbot перестал бы вклеивать вердикт строкой"))
old = OD._curator_card_text("задача", 435, {"verdict": "human", "human": CARD436,
                                            "reason": "нужен владелец"},
                            None, (700, "created", ""))
res.append(ok("создана сводная карточка владельцу (задача 700, инбокс)" in old,
              "прежние режимы карточки-отчёта (created/edited/dedup/split) не тронуты"))

# развод по операциям цел: пункт с ДВУМЯ операциями, который прибор не подтверждает
r_split, fb_split = place(CARD250, Facts(["bridge_client.py"]))
res.append(ok(r_split is not None and r_split[1] in ("split", "created"),
              "пункт 250 (мост + живые таблицы) идёт прежней веткой развода (%s)"
              % (r_split and r_split[1])))

series = os.path.join(REPO, "chain_series.json")
h0 = hashlib.sha256(open(series, "rb").read()).hexdigest() if os.path.exists(series) else None
place(CARD347, Facts(["curator_event.py"], started_after=True))
h1 = hashlib.sha256(open(series, "rb").read()).hexdigest() if os.path.exists(series) else None
res.append(ok(h0 == h1, "файл счёта серии не тронут сверкой ни на байт"))

guard_src = open(os.path.join(REPO, "pretool_guard.py"), "rb").read()
res.append(ok(b"curator_state" not in guard_src, "гард о сверке не знает — его границы не тронуты"))
exp_src = open(os.path.join(REPO, "expectations.py"), "rb").read()
res.append(ok(b"curator" not in exp_src.lower().replace(b"curator_event", b"")
              or b"curator_state" not in exp_src,
              "ожидания О1–О5 сверку не знают: их только читают"))

# ══════════════ (7) СТРАЖ ЧИСТОТЫ ═══════════════════════════════════════════════════════════
print("\n(7) страж CURATOR_STATE_PURE")
import invariants_check as IC             # noqa: E402


class Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


run = Run()
IC.check_curator_state_pure(None, run)
res.append(ok(not run.flags, "боевой curator_state.py страж проходит (%s)" % run.flags))

bad = os.path.join("/tmp", "cc_curator_state_hands_fixture.py")
open(bad, "w", encoding="utf-8").write(
    "import re\nimport subprocess\n\n\ndef go():\n    return subprocess.run(['git', 'diff'])\n")
IC._CURATOR_STATE_PATH = bad
run2 = Run()
IC.check_curator_state_pure(None, run2)
IC._CURATOR_STATE_PATH = None
res.append(ok(bool(run2.flags), "модуль С РУКАМИ страж краснит (%s)" % (run2.flags[:1] or "нет")))

run3 = Run()
IC._CURATOR_STATE_PATH = "/tmp/cc_curator_state_missing_fixture.py"
IC.check_curator_state_pure(None, run3)
IC._CURATOR_STATE_PATH = None
res.append(ok(bool(run3.flags), "файла нет → ФЛАГ (нечитаемое правило доверия не имеет)"))

print("\n%d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
