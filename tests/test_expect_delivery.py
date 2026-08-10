#!/usr/bin/env python3
"""О3 — ПРОВЕРЕННЫЙ КОММИТ ДОШЁЛ ДО ПРОДА: регресс (10.08.2026).

Владелец назвал две проверки, и обе здесь на ДОСЛОВНЫХ живых случаях основания:
    коммит не дошёл до прода            → ЗВУЧИТ           (секции 3, 4)
    доставку проверить невозможно       → говорит «НЕ ЗНАЮ» (секция 5)

Фикстуры сняты с прода, а не выдуманы: списки файлов — вывод `git log --name-only` по коммитам
7a209f7 · 1e7c93e · 51c44cd · e3e85fe; замыкания импортов — вывод `prod_drift.closure` на этой
машине; старты юнитов — журнал systemd (демон 07.08 09:24:21, splinter 09.08 19:24:34); список
расхождений диска с origin — дословный вывод живого прогона 10.08 07:34.

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение О3 живёт в том же доказанно безруком модуле
(2)  ВИДЫ ДОСТАВКИ: четыре, и «не умею» — такой же ярлык, как «умею»
(3)  ЖИВОЙ СЛУЧАЙ 51c44cd: у демона его нет → ЗВУЧИТ
(4)  ЖИВОЙ СЛУЧАЙ 7a209f7 и 1e7c93e: доставка одному потребителю не закрывает второго
(5)  ТРЕТИЙ ИСХОД: четыре дороги к «неизвестно», и ни одна не читается как «дошло»
(6)  ДВА СВИДЕТЕЛЯ: рабочий цикл «правка → рестарт → коммит» недоставкой не считается
(7)  ПОРЯДОК СИЛЫ: не доставлен > неизвестно > доставлен
(8)  ФОРМА ЗАМЕТКИ: без кнопок, без номера, без слова «да»; граница названа в тексте
(9)  ЗАДАЧИ У О3 НЕ БЫВАЕТ НИКОГДА
(10) ОТКАТ И ОКНО: порог 0 → ветка мертва ДО чтения фактов; коммит старше окна не судится
(11) ПОТОЛОК ПРОГОНА: усечение названо числом, тихих усечений нет
(12) ЗАКРЫТИЕ: только ДОКАЗАННАЯ доставка, а не исчезновение коммита из виду
(13) РУКИ: белый список git, замок «диск не сверен», факты собираются на живой машине
(14) ЖИВОЙ ПРОГОН: ни один PID не сменился, в канал не ушло ничего
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import expectations as E


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
T = E.parse_iso            # живой разборщик времени, а не своя арифметика


# ── ЖИВЫЕ ФИКСТУРЫ (сняты с прода 10.08.2026) ──────────────────────────────────────────────
CLOSURES = {
    "orchestrator-daemon": ["bridge_client.py", "card_duty.py", "curator_claim.py",
                            "curator_event.py", "curator_ops.py", "fleet_cell.py", "notify.py",
                            "orchestrator_daemon.py", "prod_drift.py", "scan_result.py",
                            "status_truth.py", "task_metrics.py"],
    "splinter": ["auditor.py", "bot.py", "bridge_client.py", "claude_client.py", "devbot.py",
                 "fleet_cell.py", "memory.py", "notify.py", "prompts.py", "report_digest.py",
                 "revizor_route.py", "scan_result.py", "spend_ledger.py", "splinter.py",
                 "task_metrics.py", "wallet_cache.py"],
}
DAEMON_START = T("2026-08-07T09:24:21Z")
SPLINTER_START = T("2026-08-09T19:24:34Z")

C_FLEET = {"sha": "51c44cd", "ct": T("2026-08-09T19:16:23Z"),
           "subject": "контракт клетки Лист1: три состояния вместо одного нуля",
           "files": ["bridge_client.py", "docs/artifacts/2026-08-09-fleet-cell-contract.md",
                     "fleet_cell.py", "invariants_check.py", "tests/fleet_cells_harness.js",
                     "tests/test_fleet_cell.py"]}
C_SCAN = {"sha": "7a209f7", "ct": T("2026-08-08T12:37:40Z"),
          "subject": "нуль по неразбору: контракт читателя живого текста + храповик в гейте",
          "files": ["blind_readers.py", "blind_readers_baseline.json", "bot.py", "devbot.py",
                    "docs/artifacts/2026-08-08-zero-on-parse-miss-contract-and-ratchet.md",
                    "gate.py", "scan_result.py", "splinter.py", "tests/test_blind_readers.py",
                    "tests/test_o3.py", "tests/test_orchestrator_stage2.py",
                    "tests/test_scan_contract.py"]}
C_INBOX = {"sha": "1e7c93e", "ct": T("2026-08-09T17:46:10Z"),
           "subject": "замок инбокса: спрашивающее не уходит мимо 1160",
           "files": ["devbot.py", "docs/artifacts/2026-08-09-inbox-lock-answerable-only.md",
                     "invariants_check.py", "tests/test_inbox_lock.py"]}
C_UNITS = {"sha": "e3e85fe", "ct": T("2026-08-07T07:49:29Z"),
           "subject": "слой ожиданий: первые два применены",
           "files": ["CLAUDE.md", "deploy/expectations.service", "deploy/expectations.timer",
                     "docs/artifacts/2026-08-07-expectations-layer-applied.md",
                     "expectations.py", "expectations_run.py", "invariants_check.py",
                     "orchestrator_daemon.py", "tests/test_expectations.py"]}

NOW = T("2026-08-10T07:34:52Z")            # момент живого прогона, с которого снят замер


def facts(commits, now=NOW, daemon=DAEMON_START, splinter=SPLINTER_START,
          mtimes=None, dirty=(), dirty_ok=True, ok_flag=True, alive=(True, True)):
    """Факты в ТОЙ ЖЕ форме, что собирают боевые руки (expectations_run.delivery_facts)."""
    mt = {}
    for c in commits:
        for rel in c["files"]:
            mt.setdefault(rel, c["ct"])    # диск переписан коммитом — обычный случай
    mt.update(mtimes or {})
    return {"now": now,
            "delivery": {"ok": ok_flag, "commits": list(commits), "closures": CLOSURES,
                         "units": {"orchestrator-daemon": {"alive": alive[0], "started": daemon},
                                   "splinter": {"alive": alive[1], "started": splinter}},
                         "mtimes": mt, "dirty": list(dirty), "dirty_ok": dirty_ok}}


CFG = E.config({})                          # боевые пороги: 4 ч, окно 48 ч


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══
print("\n(1) граница устройством: О3 добавлено в доказанно безрукий модуль")
try:
    import invariants_check as IC

    class _Run:
        def __init__(self):
            self.flags = []

        def flag(self, where, why):
            self.flags.append((where, why))

    r = _Run()
    IC.check_expectations_pure({}, r)
    res.append(ok(not r.flags, "(1) EXPECTATIONS_PURE на боевом файле молчит: %s" % (r.flags or "чисто")))
    src = open(os.path.join(REPO, "expectations.py"), encoding="utf-8").read()
    res.append(ok("subprocess" not in src and "requests" not in src,
                  "(1) в решении нет ни подпроцессов, ни сети — факты приносят руки"))
except Exception as e:                                                   # noqa: BLE001
    res.append(ok(False, "(1) инвариант: %r" % e))
    res.append(ok(False, "(1) импорты"))

# ═══ (2) ВИДЫ ДОСТАВКИ ═══
print("\n(2) четыре вида доставки: два умею проверить, два — честно нет")
KIND_CASES = [
    ("bridge_client.py", E.KIND_MEMORY, "код в памяти обоих сервисов"),
    ("scan_result.py", E.KIND_MEMORY, "код в памяти демона и splinter"),
    ("pretool_guard.py", E.KIND_DISK, "хук: отдельный процесс на вызов, ни в одном замыкании"),
    ("posttool_feed.py", E.KIND_DISK, "второй хук"),
    ("gate.py", E.KIND_DISK, "скрипт с диска"),
    ("blind_readers_baseline.json", E.KIND_DISK, "данные, читаемые при запуске"),
    ("deploy/expectations.service", E.KIND_OUTSIDE, "юнит: ставит владелец копией в /etc"),
    ("deploy/expectations.timer", E.KIND_OUTSIDE, "таймер: то же"),
    (".claude/settings.json", E.KIND_OUTSIDE, "конфиг движка: применяет владелец"),
    ("headless_settings.json", E.KIND_OUTSIDE, "конфиг: тот же вид"),
    ("ReadDocs.gs", E.KIND_OUTSIDE, "Apps Script: выкладка наружу"),
    ("requirements.txt", E.KIND_OUTSIDE, "зависимости: установка вне нашей власти"),
    ("CLAUDE.md", E.KIND_NONE, "документ — доставлять нечего"),
    ("docs/artifacts/x.md", E.KIND_NONE, "артефакт"),
    ("tests/test_fleet_cell.py", E.KIND_NONE, "тест не прод"),
    ("tests/fleet_cells_harness.js", E.KIND_NONE, "харнесс в tests/ — тоже не прод"),
    ("reports/2026-08-10/task-1.md", E.KIND_NONE, "отчёт"),
]
for path, want, why in KIND_CASES:
    got = E.file_kind(path, CLOSURES)
    res.append(ok(got == want, "(2) %-38s → %-8s (%s)" % (path, got, why)))
res.append(ok(E.consumers("bridge_client.py", CLOSURES) == ["orchestrator-daemon", "splinter"],
              "(2) потребители bridge_client.py названы оба"))
res.append(ok(E.consumers("devbot.py", CLOSURES) == ["splinter"],
              "(2) devbot.py держит только splinter"))

# ═══ (3) ЖИВОЙ СЛУЧАЙ 51c44cd — НЕ ДОШЁЛ, И ЭТО ЗВУЧИТ ═══
print("\n(3) живой случай 51c44cd (09.08 19:16 → у демона нет и сейчас)")
f = facts([C_FLEET])
st = E.delivery_state(C_FLEET, f)
res.append(ok(st["state"] == E.UNDELIVERED, "(3) исход: %s" % st["state"]))
miss = {p for p, _ in st["missing"]}
res.append(ok(miss == {"bridge_client.py", "fleet_cell.py"},
              "(3) названы РОВНО недоставленные файлы: %s" % sorted(miss)))
res.append(ok(all(u == "orchestrator-daemon" for _, u in st["missing"]),
              "(3) назван потребитель, у которого их нет: демон"))
res.append(ok(any(u == "splinter" for _, u in st["done"]),
              "(3) splinter при этом коммит получил (рестарт 19:24 после коммита 19:16)"))
vs = [v for v in E.verdict(f, CFG) if str(v.get("kind")).startswith("o3")]
res.append(ok(len(vs) == 1 and vs[0]["kind"] == "o3_undelivered",
              "(3) ЗВУЧИТ: вердикт %s" % [v["kind"] for v in vs]))
note = E.render(vs[0], "VPS")
print("      заметка: " + note)
res.append(ok("не дошёл до прода" in note and "51c44cd" in note,
              "(3) заметка называет и факт, и коммит"))
res.append(ok("bridge_client.py" in note and "orchestrator-daemon" in note,
              "(3) заметка называет файл и потребителя"))
res.append(ok(vs[0]["key"] == "o3|51c44cd", "(3) ключ эпизода — по коммиту: %s" % vs[0]["key"]))

# ═══ (4) 7a209f7 и 1e7c93e ═══
print("\n(4) доставка одному потребителю не закрывает второго")
st_scan = E.delivery_state(C_SCAN, facts([C_SCAN]))
res.append(ok(st_scan["state"] == E.UNDELIVERED, "(4) 7a209f7 → %s" % st_scan["state"]))
res.append(ok({p for p, _ in st_scan["missing"]} == {"scan_result.py"},
              "(4) у демона нет ровно scan_result.py: %s" % sorted(p for p, _ in st_scan["missing"])))
res.append(ok(any(p == "bot.py" and u == "splinter" for p, u in st_scan["done"]),
              "(4) bot.py у splinter доставлен (ручной рестарт 08.08 13:07)"))
res.append(ok(any(p == "gate.py" for p, _ in st_scan["done"]),
              "(4) gate.py доставлен фактом байт на диске (вид «с диска»)"))
st_inbox = E.delivery_state(C_INBOX, facts([C_INBOX]))
res.append(ok(st_inbox["state"] == E.DELIVERED, "(4) 1e7c93e → %s (конверт владельца 19:24)"
              % st_inbox["state"]))
res.append(ok(E.verdict(facts([C_INBOX]), CFG) == [],
              "(4) о доставленном коммите слой МОЛЧИТ — «всё хорошо» он не говорит вовсе"))

# ═══ (5) ТРЕТИЙ ИСХОД — «НЕ ЗНАЮ» ═══
print("\n(5) третий исход: неизвестно ≠ дошло")
# 5a. вид доставки нам не подотчётен (юниты systemd) — ЖИВОЙ коммит e3e85fe
f5 = facts([C_UNITS], now=C_UNITS["ct"] + 5 * 3600)
st5 = E.delivery_state(C_UNITS, f5)
res.append(ok(st5["state"] == E.UNKNOWN, "(5a) e3e85fe (юниты в deploy/) → %s" % st5["state"]))
res.append(ok({p for p, _ in st5["unknown"]} == {"deploy/expectations.service",
                                                 "deploy/expectations.timer"},
              "(5a) названы именно неподотчётные файлы: %s" % sorted(p for p, _ in st5["unknown"])))
v5 = [v for v in E.verdict(f5, CFG) if str(v.get("kind")).startswith("o3")]
res.append(ok(len(v5) == 1 and v5[0]["kind"] == "o3_unknown", "(5a) вердикт: %s"
              % [v["kind"] for v in v5]))
n5 = E.render(v5[0], "VPS")
print("      заметка: " + n5)
res.append(ok("не знаю" in n5.lower(), "(5a) заметка говорит «не знаю» ЗАГОЛОВКОМ"))
res.append(ok("НЕ «дошло»" in n5, "(5a) заметка прямо отрицает зелёное прочтение"))
res.append(ok("не дошёл до прода" not in n5, "(5a) и не выдаёт незнание за недоставку"))
# 5b. диск отличается от origin — ДОСЛОВНЫЙ живой список расхождений 10.08 07:34
f5b = facts([C_UNITS], now=C_UNITS["ct"] + 5 * 3600,
            dirty=["expectations.py", "expectations_run.py"])
st5b = E.delivery_state(C_UNITS, f5b)
res.append(ok(st5b["state"] == E.UNKNOWN, "(5b) файл на диске ≠ origin → %s" % st5b["state"]))
res.append(ok(any("на диске" in why for _, why in st5b["unknown"]),
              "(5b) причина названа: на диске лежит не то, что в origin/main"))
# 5c. git не ответил про расхождение вовсе → доставку не утверждаем НИ ПРО ОДИН файл
f5c = facts([C_INBOX], dirty_ok=False)
st5c = E.delivery_state(C_INBOX, f5c)
res.append(ok(st5c["state"] == E.UNKNOWN and not st5c["done"],
              "(5c) дерево не сверено → %s, доставленных нет вовсе" % st5c["state"]))
# 5d. процесс-потребитель не наблюдается → памяти не спросить
f5d = facts([C_FLEET], alive=(False, True), daemon=None)
st5d = E.delivery_state(C_FLEET, f5d)
res.append(ok(st5d["state"] == E.UNKNOWN, "(5d) демон не наблюдается → %s" % st5d["state"]))
res.append(ok(any("памяти не спросить" in why for _, why in st5d["unknown"]),
              "(5d) причина названа словами, а не кодом"))
res.append(ok(not any(u == "orchestrator-daemon" for _, u in st5d["missing"]),
              "(5d) мёртвый потребитель НЕ объявляется недоставкой — это разные факты"))

# ═══ (6) ДВА СВИДЕТЕЛЯ ═══
print("\n(6) рабочий цикл «правку положили → рестарт → потом коммит»")
# файл записан в 12:00, сервис поднят в 12:10, коммит лёг в 12:30 — в памяти НОВЫЙ код
cyc = {"sha": "aaaaaaa", "ct": T("2026-08-09T12:30:00Z"), "subject": "правка сначала на диск",
       "files": ["devbot.py"]}
f6 = facts([cyc], now=T("2026-08-09T20:00:00Z"), splinter=T("2026-08-09T12:10:00Z"),
           mtimes={"devbot.py": T("2026-08-09T12:00:00Z")})
res.append(ok(E.delivery_state(cyc, f6)["state"] == E.DELIVERED,
              "(6) свидетель С2 (старт позже записи файла) закрывает вопрос — не ложная тревога"))
# тот же коммит, но файл переписан ПОСЛЕ старта → ни один свидетель не сработал
f6b = facts([cyc], now=T("2026-08-09T20:00:00Z"), splinter=T("2026-08-09T12:10:00Z"),
            mtimes={"devbot.py": T("2026-08-09T12:29:00Z")})
res.append(ok(E.delivery_state(cyc, f6b)["state"] == E.UNDELIVERED,
              "(6) запись файла после старта и коммит после старта → не доставлен"))
# свидетель С1 сам по себе: старт позже коммита
f6c = facts([C_FLEET], splinter=T("2026-08-09T19:24:34Z"))
res.append(ok(any(u == "splinter" for _, u in E.delivery_state(C_FLEET, f6c)["done"]),
              "(6) свидетель С1 (старт позже коммита) достаточен сам по себе"))

# ═══ (7) ПОРЯДОК СИЛЫ ═══
print("\n(7) не доставлен > неизвестно > доставлен")
mixed = {"sha": "bbbbbbb", "ct": C_FLEET["ct"], "subject": "смешанный",
         "files": ["bridge_client.py", "deploy/expectations.timer", "gate.py"]}
st7 = E.delivery_state(mixed, facts([mixed]))
res.append(ok(st7["state"] == E.UNDELIVERED, "(7) при недоставке исход строгий: %s" % st7["state"]))
res.append(ok(st7["unknown"] and st7["done"],
              "(7) и незнание, и доставленное при этом НЕ теряются — оба в разборе"))
n7 = E.render({"kind": "o3_undelivered", "sha": "bbbbbbb", "subject": "смешанный", "age": 20000,
               "limit": 14400, "missing": st7["missing"], "unknown": st7["unknown"], "rest": 0},
              "VPS")
res.append(ok("проверить не могу" in n7, "(7) заметка называет и непроверяемую часть"))
onlyunk = {"sha": "ccccccc", "ct": C_FLEET["ct"], "subject": "только незнание",
           "files": ["deploy/expectations.timer", "gate.py"]}
res.append(ok(E.delivery_state(onlyunk, facts([onlyunk]))["state"] == E.UNKNOWN,
              "(7) доставленный сосед НЕ перекрывает незнание"))
nothing = {"sha": "ddddddd", "ct": C_FLEET["ct"], "subject": "только бумага",
           "files": ["CLAUDE.md", "docs/x.md", "tests/test_x.py"]}
res.append(ok(E.delivery_state(nothing, facts([nothing]))["state"] == E.NOTHING,
              "(7) коммит без прода = «вне доставки», а не «доставлен»"))
res.append(ok(E.verdict(facts([nothing]), CFG) == [], "(7) и он МОЛЧИТ"))

# ═══ (8) ФОРМА ЗАМЕТКИ ═══
print("\n(8) форма: информационная заметка, отвечать не на что")
for v in E.verdict(facts([C_FLEET]), CFG):
    n = E.render(v, "VPS")
    res.append(ok(n.startswith("🔔"), "(8) знак семейства ленты"))
    res.append(ok(E.TAIL in n, "(8) граница владельца названа в самом тексте"))
    # СЛОВО, а не подстрока: «да» живёт внутри «прода», и подстрочная проверка краснела бы на
    # честном тексте — тот же класс, что «красное встаёт на слово» в гарде.
    import re as _re
    res.append(ok(not _re.search(r"(?<![а-яё])да(?![а-яё])", n.lower())
                  and "подтверд" not in n.lower(),
                  "(8) слова «да»/«подтверди» нет (проверка по слову, не по подстроке)"))
    res.append(ok("#" not in n and "N=" not in n, "(8) номера карточки нет"))
    for word in ("systemctl", "systemd-run", "pkill"):
        res.append(ok(word not in n, "(8) команды перезапуска в тексте нет: %s" % word))

# ═══ (9) ЗАДАЧИ НЕ БЫВАЕТ ═══
print("\n(9) у О3 задачи не бывает никогда")
for c in (C_FLEET, C_SCAN, C_UNITS):
    for v in E.verdict(facts([c], now=c["ct"] + 40 * 3600), CFG):
        if not str(v.get("kind")).startswith("o3"):
            continue
        res.append(ok(v.get("can_task") is False, "(9) %s can_task=%s" % (v["sha"], v.get("can_task"))))
        res.append(ok(E.task_text(v) == "", "(9) %s ТЗ пустое — задачу поставить нечем" % v["sha"]))

# ═══ (10) ОТКАТ И ОКНО ═══
print("\n(10) откат порогом и окно судейства")
cfg0 = E.config({"EXPECT_DELIVER_MIN": "0"})
res.append(ok(cfg0["deliver"] == 0, "(10) EXPECT_DELIVER_MIN=0 → порог 0"))
res.append(ok([v for v in E.verdict(facts([C_FLEET]), cfg0) if str(v["kind"]).startswith("o3")] == [],
              "(10) при пороге 0 ветка мертва — ни одного вердикта О3"))
broken = {"now": NOW, "delivery": {"ok": False}}
res.append(ok(E.verdict(broken, CFG) == [], "(10) git не ответил → выборки нет → молчим"))
old = dict(C_FLEET, ct=NOW - 100 * 3600)
res.append(ok([v for v in E.verdict(facts([old], mtimes={"bridge_client.py": NOW - 100 * 3600}),
                                    CFG) if str(v["kind"]).startswith("o3")] == [],
              "(10) коммит старше окна 48 ч не судится вовсе (иначе первый прогон выкрикнет историю)"))
res.append(ok(E.config({"EXPECT_DELIVER_WINDOW_H": "1"})["deliver_window"] == 3600,
              "(10) окно читается в ЧАСАХ, а порог — в минутах"))

# ═══ (11) ПОТОЛОК ПРОГОНА ═══
print("\n(11) усечение названо числом")
many = [dict(C_FLEET, sha="x%06d" % i, ct=C_FLEET["ct"] - i * 60) for i in range(6)]
vs11 = [v for v in E.verdict(facts(many), CFG) if str(v["kind"]).startswith("o3")]
res.append(ok(len(vs11) == E.O3_CAP, "(11) за прогон объявлено не больше %d: %d"
              % (E.O3_CAP, len(vs11))))
res.append(ok(all(v["rest"] == 6 - E.O3_CAP for v in vs11),
              "(11) остаток назван числом: %s" % {v["rest"] for v in vs11}))
res.append(ok("ещё 3" in E.render(vs11[0], "VPS"), "(11) и он ВИДЕН в заметке"))
res.append(ok([v["sha"] for v in vs11] == sorted([v["sha"] for v in vs11],
                                                 key=lambda s: -int(s[1:])),
              "(11) первыми идут САМЫЕ СТАРЫЕ ожидания"))

# ═══ (12) ЗАКРЫТИЕ ЭПИЗОДА ═══
print("\n(12) закрытие: только доказанная доставка")
key = "o3|51c44cd"
after = facts([C_FLEET], daemon=T("2026-08-10T06:00:00Z"))     # демон перезапущен → доставлен
res.append(ok(E.delivery_state(C_FLEET, after)["state"] == E.DELIVERED,
              "(12) после рестарта демона коммит доставлен"))
res.append(ok(E.closures(after, CFG, [key]) == [key], "(12) эпизод закрывается"))
res.append(ok("51c44cd" in E.render_close(key, "VPS"),
              "(12) закрытие называет коммит: %s" % E.render_close(key, "VPS")))
res.append(ok(E.closures(facts([C_FLEET]), CFG, [key]) == [],
              "(12) пока нарушение живо — не закрываем"))
res.append(ok(E.closures(facts([C_INBOX]), CFG, [key]) == [],
              "(12) коммит пропал из выборки → это НЕ выздоровление, эпизод остаётся открыт"))
res.append(ok(E.closures({"now": NOW, "delivery": {"ok": False}}, CFG, [key]) == [],
              "(12) источник фактов молчит → не закрываем"))

# ═══ (13) РУКИ ═══
print("\n(13) руки: белый список git и сбор фактов на живой машине")
try:
    import expectations_run as ER
    res.append(ok(ER._git(["push", "origin", "main"]) is None,
                  "(13) подкоманда вне белого списка не исполняется вовсе"))
    res.append(ok(ER._git(["commit", "-m", "x"]) is None, "(13) то же для записи в историю"))
    res.append(ok("diff" in ER.GIT_READ_RUN and "push" not in ER.GIT_READ_RUN,
                  "(13) белый список читающий: %s" % sorted(ER.GIT_READ_RUN)))
    d = ER.delivery_facts(__import__("time").time())
    res.append(ok(d.get("ok") is True, "(13) факты собраны на живой машине: ok=%s" % d.get("ok")))
    res.append(ok(isinstance(d.get("dirty_ok"), bool) and isinstance(d.get("dirty"), list),
                  "(13) замок «диск сверен с origin» отвечает: dirty_ok=%s, расхождений %d"
                  % (d.get("dirty_ok"), len(d.get("dirty") or []))))
    res.append(ok(set(d.get("closures") or {}) == {"orchestrator-daemon", "splinter"},
                  "(13) потребители те же, что у детектора дрейфа: %s" % sorted(d.get("closures") or {})))
    res.append(ok(all(isinstance(v, dict) and "alive" in v for v in (d.get("units") or {}).values()),
                  "(13) про каждого потребителя сказано, наблюдается ли он"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(13) руки")] * 7

# ═══ (14) ЖИВОЙ ПРОГОН ═══
print("\n(14) живой прогон: ничего не тронуто, ничего не отправлено")
try:
    import time as _t
    import expectations_run as ER

    def pids():
        out = {}
        for unit, entry in (("orchestrator-daemon", "orchestrator_daemon.py"),
                            ("splinter", "bot.py")):
            p = ER._proc(unit, entry)
            out[unit] = (p or {}).get("pid")
        return out

    before = pids()
    sent = []
    _note, _enq, _q = ER.send_note, ER.enqueue_escalation, ER.queue_facts
    ER.send_note = lambda t: (sent.append(t), True)[1]
    ER.enqueue_escalation = lambda v: sent.append(("task", v)) or 0
    ER.queue_facts = lambda: {"ok": False, "rows": []}
    try:
        out = ER.run(dry=True)
    finally:
        ER.send_note, ER.enqueue_escalation, ER.queue_facts = _note, _enq, _q
    after = pids()
    res.append(ok(before == after and any(before.values()),
                  "(14) PID живых процессов не сменились: %s" % before))
    res.append(ok(sent == [], "(14) в канал не ушло ничего"))
    res.append(ok(out.get("tasks") == [], "(14) задач не поставлено"))
    o3keys = [k for k in out.get("notes", []) if str(k).startswith("o3|")]
    print("      вердикты О3 на живых фактах: %s" % o3keys)
    res.append(ok(isinstance(o3keys, list), "(14) прогон завершился без исключений"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(14) живой прогон")] * 4

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
