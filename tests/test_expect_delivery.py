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
(15) ПРИЧИНА расхождения диска названа, а вердикт не тронут
(16) ОТСРОЧКА объявления окна правки: тот же вердикт, другой момент; оба замка против слепоты
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
# АДРЕС НАБЛЮДЕНИЯ ЗАФИКСИРОВАН НА ДО-13.08: секция (16) судит РУКИ и меряет ОТСРОЧКУ ОКНА
# ПРАВКИ (30 мин) — её голдены стоят на том, что пережившее отсрочку уходит владельцу СРАЗУ.
# С 13.08 поверх лежит вторая отсрочка (адрес, 60 мин), и без этой строки секция мерила бы
# сумму двух правил вместо своего. Предмет секции не изменён; новый адрес судит свой регресс
# tests/test_expect_journal.py. Форсируем, а не setdefault (класс CURATOR: env демона).
os.environ["EXPECT_TO_BRAIN"] = "0"

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
    # Предмет проверки — ТОЖДЕСТВО двух списков, как и говорит её название, а не то, что в них
    # ровно два имени. Литерал `{"orchestrator-daemon", "splinter"}` замораживал СНИМОК списка:
    # 06.09.2026 владелец внёс в наблюдаемые `wa-webhook`, и проверка покраснела на согласованном
    # изменении, вместо того чтобы стеречь рассогласование. Теперь она сверяет О3 с самим
    # `prod_drift.WATCHED` и краснеет в ОБЕ стороны — если списки разойдутся хоть на одно имя.
    import prod_drift as _PD
    res.append(ok(set(d.get("closures") or {}) == {u for u, _ in _PD.WATCHED},
                  "(13) потребители те же, что у детектора дрейфа: %s" % sorted(d.get("closures") or {})))
    res.append(ok("wa-webhook" in {u for u, _ in _PD.WATCHED},
                  "(13) `wa-webhook` среди наблюдаемых (решение владельца 06.09.2026)"))
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

# ═══ (15) ПРИЧИНА РАСХОЖДЕНИЯ ДИСКА НАЗВАНА, А ВЕРДИКТ НЕ ТРОНУТ (10.08.2026, цель 458) ═══
# Живой случай ДОСЛОВНО: 10.08 19:29:56 наблюдатель дал o3_unknown про 7bcddba, потому что
# orchestrator_daemon.py лежал правленым с 19:20:32; коммит a59ce6e закрыл окно в 19:35:55
# (15 м 23 с), и в 19:40:12 боевой журнал закрыл эпизод. Замер реплеем за 7 суток: 341 из 341
# таких вердиктов — правка МОЛОЖЕ судимого коммита.
print("\n(15) причина названа, вердикт прежний (живой случай 7bcddba / a59ce6e)")
C_O2FIX = {"sha": "7bcddba", "ct": T("2026-08-10T08:05:04Z"),
           "subject": "О2: идущий заход — работа, а не остановка",
           "files": ["CLAUDE.md", "expectations.py", "orchestrator_daemon.py",
                     "tests/test_expectations.py"]}
LIVE_NOW = T("2026-08-10T19:29:56Z")            # такт, на котором заметка ушла в ленту
LIVE_MT = T("2026-08-10T19:20:32Z")             # mtime orchestrator_daemon.py в тот момент
f15 = facts([C_O2FIX], now=LIVE_NOW, daemon=T("2026-08-10T08:08:56Z"),
            dirty=["orchestrator_daemon.py"], mtimes={"orchestrator_daemon.py": LIVE_MT})
st15 = E.delivery_state(C_O2FIX, f15)
# 15a. ВЕРДИКТ НЕ ИЗМЕНИЛСЯ — это главное требование ТЗ, а не побочная проверка.
res.append(ok(st15["state"] == E.UNKNOWN,
              "(15a) вердикт остался «неизвестно»: %s" % st15["state"]))
res.append(ok(not any(p == "orchestrator_daemon.py" for p, _ in st15["done"] + st15["missing"]),
              "(15a) разошедшийся файл НЕ объявлен ни доставленным, ни недоставкой"))
why15 = dict((p, w) for p, w in st15["unknown"]).get("orchestrator_daemon.py", "")
print("      причина: " + why15)
res.append(ok(E.DIRTY_WHY in why15, "(15b) прежняя формулировка НЕ выброшена, а дополнена"))
res.append(ok(E.DIRTY_WIP in why15, "(15b) названа причина: правка моложе коммита"))
res.append(ok("11 ч 15 мин" in why15,
              "(15b) названо ЧИСЛО — насколько правка моложе коммита (19:20:32 − 08:05:04)"))
v15 = [v for v in E.verdict(f15, CFG) if str(v.get("kind")).startswith("o3")]
res.append(ok(len(v15) == 1 and v15[0]["kind"] == "o3_unknown",
              "(15c) вид вердикта прежний: %s" % [v["kind"] for v in v15]))
n15 = E.render(v15[0], "VPS")
print("      заметка: " + n15)
res.append(ok("не знаю" in n15.lower() and "НЕ «дошло»" in n15,
              "(15c) заголовок и отрицание зелёного прочтения на месте"))
res.append(ok("рабочий цикл" in n15 and "закроется сам" in n15,
              "(15c) причина названа В ТЕКСТЕ ЗАМЕТКИ отдельной строкой"))
res.append(ok("вердикт всё равно «не знаю»" in n15,
              "(15c) и та же строка прямо повторяет, что вердикт НЕ смягчён"))
res.append(ok("не дошёл до прода" not in n15, "(15c) незнание не выдаётся за недоставку"))
# 15d. ОБРАТНЫЙ СЛУЧАЙ (за 7 суток замера — ноль): правка СТАРШЕ коммита звучит иначе.
f15d = facts([C_O2FIX], now=LIVE_NOW, daemon=T("2026-08-10T08:08:56Z"),
             dirty=["orchestrator_daemon.py"],
             mtimes={"orchestrator_daemon.py": T("2026-08-10T07:00:00Z")})
why15d = dict((p, w) for p, w in E.delivery_state(C_O2FIX, f15d)["unknown"]).get(
    "orchestrator_daemon.py", "")
print("      причина (правка старше): " + why15d)
res.append(ok(E.delivery_state(C_O2FIX, f15d)["state"] == E.UNKNOWN,
              "(15d) и здесь вердикт «неизвестно» — различитель судит ТЕКСТ, не исход"))
res.append(ok(E.DIRTY_WIP not in why15d and "СТАРШЕ" in why15d,
              "(15d) странный случай назван странным, а не рутиной"))
res.append(ok("рабочий цикл" not in E.render(
    [v for v in E.verdict(f15d, CFG) if str(v.get("kind")).startswith("o3")][0], "VPS"),
    "(15d) объяснения «это просто работа» на нём НЕ появляется"))
# 15e. ФАКТА О ЗАПИСИ НЕТ → прежняя строка БАЙТ-В-БАЙТ, без догадок.
f15e = facts([C_O2FIX], now=LIVE_NOW, dirty=["orchestrator_daemon.py"])
f15e["delivery"]["mtimes"] = {}
why15e = dict((p, w) for p, w in E.delivery_state(C_O2FIX, f15e)["unknown"]).get(
    "orchestrator_daemon.py", "")
res.append(ok(why15e == E.DIRTY_WHY, "(15e) mtime неизвестен → прежний текст без изменений"))
res.append(ok(E.dirty_why("x.py", 0, {"x.py": 1.0}) == E.DIRTY_WHY,
              "(15e) времени коммита нет → тоже прежний текст"))
res.append(ok(E.dirty_why("x.py", 100.0, {"x.py": "мусор"}) == E.DIRTY_WHY,
              "(15e) мусор вместо mtime не роняет разбор и не рождает догадку"))
# 15f. ЗАМОК ЦЕЛ: сила исходов не переставлена, «неизвестно» по-прежнему бьёт «доставлен».
f15f = facts([C_O2FIX], now=LIVE_NOW, daemon=T("2026-08-10T08:08:56Z"),
             dirty=["expectations.py"], mtimes={"expectations.py": LIVE_MT})
st15f = E.delivery_state(C_O2FIX, f15f)
res.append(ok(st15f["state"] == E.UNKNOWN and any(u == "orchestrator-daemon"
                                                  for _p, u in st15f["done"]),
              "(15f) один файл доставлен, другой неизвестен → исход всё равно «неизвестно»"))
# 15g. Замер приложен к делу: у обеих веток есть свой корпус, и он назван в модуле.
res.append(ok("341" in (E.__doc__ or "") and "a59ce6e" in (E.__doc__ or ""),
              "(15g) числа замера и живой случай названы в самом модуле, а не только в артефакте"))

# ═══ (16) ОТСРОЧКА ОБЪЯВЛЕНИЯ ОКНА ПРАВКИ: ВЕРДИКТ ТОТ ЖЕ, МОМЕНТ ДРУГОЙ (10.08.2026) ═══
# Основание — тот же замер: 341 из 341, медиана жизни эпизода 20 мин, окно «правка → коммит»
# по 178 файлам медиана 5 / p90 15 мин. Величина отсрочки = 30 мин (два p90, три такта).
# ЗДЕСЬ ЖЕ ОБА ЗАМКА ПРОТИВ СЛЕПОТЫ, названные ТЗ: переживший отсрочку объявляется обязательно
# (16e), а правка СТАРШЕ коммита не откладывается ВООБЩЕ (16b).
print("\n(16) отсрочка объявления: вердикт не тронут, замки против слепоты на месте")
CFG_D = E.config({"EXPECT_DIRTY_DEFER_MIN": "30"})
CFG_OFF = E.config({"EXPECT_DIRTY_DEFER_MIN": "0"})
DEFER = CFG_D["dirty_defer"]
res.append(ok(DEFER == 1800.0 and E.config({})["dirty_defer"] == 1800.0,
              "(16) боевая отсрочка 30 мин и по умолчанию, и явным ключом: %s" % DEFER))

# 16a. ОКНО ПРАВКИ (живой случай 7bcddba) — единственный откладываемый исход.
st16 = E.delivery_state(C_O2FIX, f15)
res.append(ok(E.o3_defer(st16, CFG_D) == DEFER,
              "(16a) окно правки откладывается на %s" % E.human_age(E.o3_defer(st16, CFG_D))))
v16 = [v for v in E.verdict(f15, CFG_D) if str(v.get("kind")).startswith("o3")]
v16z = [v for v in E.verdict(f15, CFG_OFF) if str(v.get("kind")).startswith("o3")]
FIELDS = ("kind", "key", "sha", "state", "missing", "unknown", "age", "limit", "can_task")
res.append(ok([{k: v[k] for k in FIELDS} for v in v16] == [{k: v[k] for k in FIELDS} for v in v16z],
              "(16a) ВЕРДИКТ НЕ ИЗМЕНЁН НИ ОДНИМ ПОЛЕМ — отложен только момент объявления"))
res.append(ok(v16[0]["defer"] == DEFER and v16z[0]["defer"] == 0.0,
              "(16a) отсрочка живёт ОТДЕЛЬНЫМ полем, а откат гасит её до разбора"))
res.append(ok(st16["state"] == E.UNKNOWN and E.delivery_state(C_O2FIX, f15)["state"] == E.UNKNOWN,
              "(16a) исход как был: «%s»" % st16["state"]))

# 16b. ЗАМОК: правка СТАРШЕ коммита (за 341 случай — ноль) НЕ откладывается вовсе.
st16b = E.delivery_state(C_O2FIX, f15d)
res.append(ok(E.o3_defer(st16b, CFG_D) == 0.0,
              "(16b) правка СТАРШЕ коммита объявляется НЕМЕДЛЕННО: отсрочка %s"
              % E.o3_defer(st16b, CFG_D)))
res.append(ok(E.DIRTY_WIP not in dict(st16b["unknown"]).get("orchestrator_daemon.py", ""),
              "(16b) и различает их та же причина, что и в тексте заметки"))

# 16c. ЗАМОК: любая ДРУГАЯ причина рядом — и отсрочки нет. Пять дорог, каждая на живых фикстурах.
f16_und = facts([C_FLEET])                                   # недоставка — не ждёт никогда
f16_mix = facts([C_O2FIX], now=LIVE_NOW, daemon=T("2026-08-10T08:08:56Z"),
                dirty=["orchestrator_daemon.py", "expectations.py"],
                mtimes={"orchestrator_daemon.py": LIVE_MT})  # одно окно + одна другая причина
f16_tree = facts([C_O2FIX], now=LIVE_NOW, dirty=["orchestrator_daemon.py"],
                 mtimes={"orchestrator_daemon.py": LIVE_MT}, dirty_ok=False)
f16_proc = facts([C_FLEET], now=LIVE_NOW, alive=(False, True))   # памяти не у кого спросить
f16_out = facts([C_UNITS], now=LIVE_NOW)                     # вид доставки неподотчётен
for label, ff, cc in (("недоставка", f16_und, C_FLEET), ("причина другого рода", f16_mix, C_O2FIX),
                      ("дерево не сверено", f16_tree, C_O2FIX),
                      ("процесс не наблюдается", f16_proc, C_FLEET),
                      ("вид неподотчётен", f16_out, C_UNITS)):
    res.append(ok(E.o3_defer(E.delivery_state(cc, ff), CFG_D) == 0.0,
                  "(16c) «%s» → говорим сразу" % label))

# ── РУКИ: отсрочку исполняют они, и обе половины замка проверяются сквозным прогоном ──
try:
    import expectations_run as ER

    def drive(ticks, defer_min="30"):
        """Прогнать руки по тактам. Состояние — в памяти, боевой /tmp и reports/ не трогаем."""
        os.environ["EXPECT_DIRTY_DEFER_MIN"] = str(defer_min)
        box, sent, outs = {"st": {}}, [], []
        keep = (ER.load_state, ER.save_state, ER.snapshot, ER.send_note, ER.write_proof,
                ER.enqueue_escalation)
        ER.load_state = lambda: dict(box["st"])
        ER.save_state = lambda s: box.__setitem__("st", dict(s))
        ER.send_note = lambda t: (sent.append(t), True)[1]
        ER.write_proof = lambda v, f, n: ""
        ER.enqueue_escalation = lambda v: 0
        try:
            for tnow, ff in ticks:
                ER.snapshot = lambda a=None, b=None, c=None, _f=ff: _f
                outs.append(ER.run(now=tnow))
        finally:
            (ER.load_state, ER.save_state, ER.snapshot, ER.send_note, ER.write_proof,
             ER.enqueue_escalation) = keep
            os.environ.pop("EXPECT_DIRTY_DEFER_MIN", None)
        return outs, sent, box["st"]

    def window_facts(t):
        """Окно правки на такте t: файл лежит правленым, коммит доставлен ещё утром."""
        return facts([C_O2FIX], now=t, daemon=T("2026-08-10T08:08:56Z"),
                     dirty=["orchestrator_daemon.py"], mtimes={"orchestrator_daemon.py": LIVE_MT})

    TICKS = [LIVE_NOW + i * 600.0 for i in range(6)]
    KEY = "o3|7bcddba"

    # 16d. ОТКАТ: отсрочки нет → заметка на ПЕРВОМ такте, как было до правки.
    o, sent, _st = drive([(TICKS[0], window_facts(TICKS[0]))], defer_min="0")
    res.append(ok(o[0]["notes"] == [KEY] and len(sent) == 1 and not o[0]["held"],
                  "(16d) EXPECT_DIRTY_DEFER_MIN=0 → прежнее поведение: заметка сразу"))

    # 16e. ЗАМОК ПРОТИВ СЛЕПОТЫ: эпизод, ПЕРЕЖИВШИЙ отсрочку, объявляется ОБЯЗАТЕЛЬНО.
    o, sent, stt = drive([(t, window_facts(t)) for t in TICKS[:5]])
    held = [i for i, r in enumerate(o) if r["held"]]
    noted = [i for i, r in enumerate(o) if r["notes"]]
    res.append(ok(held == [0, 1, 2] and noted == [3],
                  "(16e) три такта молчания, на четвёртом (30 мин) заметка: держали %s, сказали %s"
                  % (held, noted)))
    res.append(ok(len(sent) == 1, "(16e) и ровно ОДНА заметка за пять тактов: %d" % len(sent)))
    res.append(ok("держал заметку 30 мин" in sent[0] and "отсрочка не отмена" in sent[0],
                  "(16e) заметка САМА называет, сколько её держали"))
    res.append(ok(E.DIRTY_WHY in sent[0] and "не знаю" in sent[0].lower(),
                  "(16e) и остаётся тем же вердиктом, что был бы без отсрочки"))
    res.append(ok(all(r["verdicts"] == 1 for r in o),
                  "(16e) ОСТАЁТСЯ В СЧЁТЕ на каждом такте: %s" % [r["verdicts"] for r in o]))
    res.append(ok(float((stt.get("open") or {}).get(KEY, {}).get("first") or 0) == TICKS[0],
                  "(16e) память о ПЕРВОМ обнаружении пережила прогоны — иначе отсрочка вечна"))

    # 16f. ЭПИЗОД, ЗАКРЫВШИЙСЯ РАНЬШЕ ОТСРОЧКИ: владелец не увидел НИЧЕГО — ни заметки, ни
    #      закрытия. Но из счёта он не исчез.
    done = facts([C_O2FIX], now=TICKS[1], daemon=T("2026-08-10T19:00:00Z"))   # правка уехала
    o, sent, stt = drive([(TICKS[0], window_facts(TICKS[0])), (TICKS[1], done)])
    res.append(ok(sent == [], "(16f) в канал не ушло НИЧЕГО: %s" % sent))
    res.append(ok(o[0]["held"] == [KEY] and o[1]["quiet"] == [KEY] and o[1]["closed"] == [],
                  "(16f) эпизод погашен отсрочкой, а не «закрыт» заметкой: %s" % o[1]))
    res.append(ok(int((stt.get("quiet") or {}).get("n") or 0) == 1
                  and KEY in ((stt.get("quiet") or {}).get("last") or []),
                  "(16f) но в счёте остался: %s" % stt.get("quiet")))
    res.append(ok(KEY not in (stt.get("open") or {}),
                  "(16f) и не завис открытым эпизодом навсегда"))

    # 16g. ЗАМОК: исход СМЕНИЛСЯ на недоставку внутри отсрочки → говорим НЕМЕДЛЕННО, не досиживая.
    # демон поднят ДО коммита, а файл переписан ПОСЛЕ его старта → не сработал ни один свидетель
    undel = facts([C_O2FIX], now=TICKS[1], daemon=T("2026-08-10T07:00:00Z"),
                  mtimes={"orchestrator_daemon.py": T("2026-08-10T09:30:00Z")})
    o, sent, _st = drive([(TICKS[0], window_facts(TICKS[0])), (TICKS[1], undel)])
    res.append(ok(o[0]["held"] == [KEY] and o[1]["notes"] == [KEY] and len(sent) == 1,
                  "(16g) недоставка, вскрывшаяся под окном правки, ждать не стала: %s" % o[1]))
    res.append(ok("не дошёл до прода" in sent[0] and "держал заметку 10 мин" in sent[0],
                  "(16g) и заметка честно называет и исход, и то, что 10 минут её держали"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(16) руки: отсрочка")] * 13

# ═══ (17) ДОСТАВКА СУДИТСЯ ПО СОДЕРЖИМОМУ ФАЙЛА, А НЕ ПО ЧИСТОТЕ ДЕРЕВА (15.08.2026) ═══
# ЖИВОЙ СЛУЧАЙ 10:17 15.08: горячий `invariants_check.py` тронут ОДИННАДЦАТЬЮ коммитами окна
# фактов — и одной незакоммиченной правкой в нём все одиннадцать становились «неизвестными»
# РАЗОМ. Фикстура дословная: шаблоны файлов — вывод `git log --name-only`, блобы — вывод
# `git rev-parse <коммит>:invariants_check.py`, старты юнитов — журнал systemd того утра
# (splinter 15.08 03:14:41, демон 15.08 05:28:09), то есть ПОЗЖЕ всех одиннадцати.
print("\n(17) вердикт О3 по содержимому файла: грязь соседа больше не хоронит коммит")
HOT11 = [
    ("baf5d30", 1786731717, "37a5042924b113756c35427fbf40673ebc711edd",
     ["CLAUDE.md", "docs/artifacts/2026-08-14-named-work-in-history.md", "invariants_check.py",
      "splinter.py", "tests/test_work_name.py", "work_name.py"]),
    ("f70f186", 1786723187, "77b81a339f2d4460d4550eb10896f37c59d44e4b",
     ["CLAUDE.md", "docs/artifacts/2026-08-14-undo-last-service-record.md",
      "docs/knowledge_base.md", "invariants_check.py", "splinter.py", "tests/test_undo_last.py",
      "undo_last.py"]),
    ("4db98fe", 1786716983, "7796c07b0272c0a1379058bf12628f525a04aca3",
     ["docs/artifacts/2026-08-14-odo-ceiling.md", "docs/knowledge_base.md",
      "invariants_check.py", "odo_ceiling.py", "splinter.py", "tests/test_odo_ceiling.py",
      "write_fact.py"]),
    ("1552fab", 1786710424, "094b2d7c11c080ef70e642adabece1df0a11527c",
     ["CLAUDE.md", "deliver_card.py", "docs/artifacts/2026-08-14-deliver-card-path-c.md",
      "invariants_check.py", "orchestrator_daemon.py", "tests/test_deliver_card.py"]),
    ("82caf4c", 1786707340, "b65f3585ec45ce05e2a068322d3f917dd7710cf3",
     ["CLAUDE.md", "bridge_client.py", "docs/artifacts/2026-08-14-queue-state-in-brain.md",
      "expectations_run.py", "invariants_check.py", "queue_state.py",
      "tests/test_queue_state.py"]),
    ("d5d5c19", 1786704178, "f171ed49eef164386d595d1d4525986fdbb5539a",
     ["CLAUDE.md", "devbot.py", "docs/artifacts/2026-08-14-revizor-tick-age.md",
      "invariants_check.py", "revizor_age.py", "tests/test_revizor_age.py",
      "tests/test_status_summary.py"]),
    ("497c857", 1786701152, "8ae6f9ad9e00353d4a1e5a545a9a8d464b0a51f3",
     ["CLAUDE.md", "docs/artifacts/2026-08-14-service-receipt-both-halves.md",
      "docs/knowledge_base.md", "invariants_check.py", "service_receipt.py", "splinter.py",
      "tests/test_service_receipt.py"]),
    ("a4489a5", 1786653455, "8d65e75426fda6e1cac92f3db3ef15969bc6bd3a",
     ["CLAUDE.md", "balance_fact.py", "docs/artifacts/2026-08-13-cash-balance-not-verified.md",
      "docs/knowledge_base.md", "invariants_check.py", "splinter.py",
      "tests/test_cash_balance_fact.py", "tests/test_deposit_link.py", "wallet_cache.py"]),
    ("c3e5543", 1786634284, "246a6ad2ab1b2f1c22c6cbfa585c08a862221dd7",
     ["docs/artifacts/2026-08-13-mirror-sync-by-fact.md", "docs/knowledge_base.md",
      "invariants_check.py", "splinter.py", "tests/test_write_fact.py", "write_fact.py"]),
    ("a9ac39a", 1786629117, "08d424f7b35acfa2bff99cb4508516b24806acd5",
     ["CLAUDE.md", "docs/artifacts/2026-08-13-observations-go-to-brain.md", "expect_journal.py",
      "expectations.py", "expectations_run.py", "invariants_check.py",
      "tests/test_expect_delivery.py", "tests/test_expect_journal.py",
      "tests/test_expect_pc_bridge.py", "tests/test_expectations.py"]),
    ("9a23c61", 1786615411, "7772213bc93494cd89a879aa04ff72b9652c5fc8",
     ["CLAUDE.md", "bridge_client.py", "card_deadline.py",
      "docs/artifacts/2026-08-13-info-card-deadline.md", "invariants_check.py", "splinter.py",
      "tests/test_info_card_deadline.py"]),
]
NOW17 = T("2026-08-15T10:17:00Z")
D17, S17 = T("2026-08-15T05:28:09Z"), T("2026-08-15T03:14:41Z")   # журнал systemd того утра
HOT = "invariants_check.py"
WIP_BLOB = "f" * 40                        # правка на диске: такого блоба нет ни в одном коммите
C17 = [{"sha": s, "ct": ct, "subject": "живой коммит окна", "files": list(fs)}
       for s, ct, _b, fs in HOT11]
BLOBS17 = {HOT: {s: b for s, _ct, b, _fs in HOT11}}


def hot_facts(disk_blob, hot_mtime, blobs=BLOBS17, dirty=(HOT,), dirty_ok=True, commits=C17):
    """Факты той же формы, что собирают боевые руки, — с двумя хешами про спорный файл."""
    f = facts(commits, now=NOW17, daemon=D17, splinter=S17,
              mtimes={HOT: hot_mtime}, dirty=dirty, dirty_ok=dirty_ok)
    f["delivery"]["blobs"] = blobs
    f["delivery"]["disk"] = {HOT: disk_blob} if disk_blob else {}
    return f


def states(f):
    return [E.delivery_state(c, f)["state"] for c in C17]


def collections_count(rows):
    """«исход×сколько» — число в голдене, а не пересказ (правило «сводка гипотеза, числа факт»)."""
    return ", ".join("%s×%d" % (s, rows.count(s)) for s in sorted(set(rows)))


try:
    # 17a. ДО ПРАВКИ (фактов о содержимом нет — прежний код) — все ОДИННАДЦАТЬ «неизвестно».
    before = states(hot_facts(None, NOW17 - 60, blobs={}))
    res.append(ok(before.count(E.UNKNOWN) == 11,
                  "(17a) прежнее правило: один грязный файл → 11 «неизвестно» разом: %s"
                  % collections_count(before)))

    # 17b. ПОСЛЕ: незакоммиченная правка, написанная ПОЗЖЕ всех одиннадцати, легла ПОВЕРХ них.
    after = states(hot_facts(WIP_BLOB, NOW17 - 60))
    res.append(ok(after.count(E.UNKNOWN) == 0 and after.count(E.DELIVERED) == 11,
                  "(17b) по содержимому: те же 11 судятся и все доставлены: %s"
                  % collections_count(after)))
    why = E.disk_carries(HOT, C17[-1], hot_facts(WIP_BLOB, NOW17 - 60))
    res.append(ok(why[0] is True and "ПОЗЖЕ коммита" in why[1] and "ПОВЕРХ" in why[1],
                  "(17b) и причина названа словами, а не молчанием: %s" % (why[1],)))

    # 17c. ЛОКАЛЬНЫЙ КОММИТ, ЕЩЁ НЕ ЗАПУШЕННЫЙ: на диске содержимое НОВЕЙШЕГО из одиннадцати —
    # старшие им перекрыты, а не потеряны (в этом репозитории случай ежедневный).
    newer = hot_facts(HOT11[0][2], NOW17 - 60)
    res.append(ok(states(newer).count(E.UNKNOWN) == 0,
                  "(17c) содержимое более нового коммита закрывает и старшие: %s"
                  % collections_count(states(newer))))
    v = E.disk_carries(HOT, C17[-1], newer)
    res.append(ok(v[0] is True and "baf5d30" in v[1] and "перекрыт" in v[1],
                  "(17c) и заметка называет ИМЕННО тот коммит, чьё содержимое лежит: %s" % (v[1],)))

    # 17d. ЗАМОК ← ОТКАТ НАЗАД. На диске содержимое СТАРЕЙШЕГО, судим НОВЕЙШИЙ: это не «дошло»
    # и не «не дошло» — рестарт такого не лечит. Третий исход остаётся, и он назван вслух.
    back = hot_facts(HOT11[-1][2], NOW17 - 60)
    st = E.delivery_state(C17[0], back)
    res.append(ok(st["state"] == E.UNKNOWN
                  and any("откатили назад" in w for _p, w in st["unknown"]),
                  "(17d) откат дерева назад → «неизвестно» со странной причиной: %s"
                  % (st["unknown"][:1],)))

    # 17e. ЗАМОК ← НАСТОЯЩАЯ НЕДОСТАВКА ОБЪЯВЛЯЕТСЯ. Живой случай 15.08: 107b7ce правит
    # bridge_client.py (память обоих юнитов), а оба подняты РАНЬШЕ него; рядом грязен сосед.
    C_LIVE = {"sha": "107b7ce", "ct": T("2026-08-15T10:23:58Z"),
              "subject": "журнал таймаута называет ВЫДАННОЕ плечо",
              "files": ["CLAUDE.md", "bridge_client.py", "tests/test_timeout_leg_log.py"]}
    live = hot_facts(WIP_BLOB, T("2026-08-15T10:40:00Z"), commits=[C_LIVE] + C17)
    live["delivery"]["mtimes"]["bridge_client.py"] = T("2026-08-15T10:23:00Z")
    live["now"] = T("2026-08-15T10:46:00Z")
    stl = E.delivery_state(C_LIVE, live)
    res.append(ok(stl["state"] == E.UNDELIVERED and len(stl["missing"]) == 2,
                  "(17e) недоставка при грязном соседе ЗВУЧИТ, а не тонет: %s" % (stl["missing"],)))
    res.append(ok(states(live).count(E.UNKNOWN) == 0,
                  "(17e) и соседние одиннадцать в это же время судятся по существу"))

    # 17f. ТРЕТИЙ ИСХОД ← ПРАВКА СТАРШЕ КОММИТА: содержимое ниоткуда не опознано, времени
    # правки нечем объяснить — прежнее «неизвестно» с прежней формулировкой.
    old = hot_facts(WIP_BLOB, T("2026-08-13T09:00:00Z"))
    sto = E.delivery_state(C17[0], old)
    res.append(ok(sto["state"] == E.UNKNOWN
                  and any("СТАРШЕ коммита" in w for _p, w in sto["unknown"]),
                  "(17f) правка старше коммита осталась «неизвестно»: %s" % (sto["unknown"][:1],)))

    # 17g. ТРЕТИЙ ИСХОД ← ХЕШЕЙ НЕ СНЯЛИ: ветка байт-в-байт прежняя, вместе с причиной, форму
    # которой читает o3_defer (отсрочка окна правки не тронута ни на бит).
    blind = hot_facts(None, NOW17 - 60, blobs={})
    stb = E.delivery_state(C17[0], blind)
    res.append(ok(stb["state"] == E.UNKNOWN
                  and any(E.DIRTY_WIP in w for _p, w in stb["unknown"]),
                  "(17g) без хешей — прежнее «неизвестно» и прежняя причина: %s"
                  % (stb["unknown"][:1],)))
    res.append(ok(E.o3_defer({"state": E.UNKNOWN, "missing": [], "unknown": stb["unknown"]},
                             {"dirty_defer": 30.0}) == 30.0,
                  "(17g) и отсрочка окна правки работает ровно как работала"))

    # 17h. ЗАМОК ← ДЕРЕВО НЕ СВЕРЕНО СИЛЬНЕЕ ЛЮБОГО СОДЕРЖИМОГО: спросить не смогли — не судим.
    nogit = hot_facts(HOT11[0][2], NOW17 - 60, dirty_ok=False)
    res.append(ok(states(nogit).count(E.UNKNOWN) == 11,
                  "(17h) «дерево с origin не сверено» бьёт содержимое: %s"
                  % collections_count(states(nogit))))

    # 17i. ГРАНИЦА: коммит, тронувший ТОЛЬКО неподотчётный вид, содержимым не спасается.
    C_OUT = {"sha": "abc1234", "ct": NOW17 - 7200, "subject": "выкладка",
             "files": ["bridge_prod/Bridge.js"]}
    stx = E.delivery_state(C_OUT, hot_facts(WIP_BLOB, NOW17 - 60, commits=[C_OUT]))
    res.append(ok(stx["state"] == E.UNKNOWN and "не умею" in stx["unknown"][0][1],
                  "(17i) неподотчётный вид доставки не тронут: %s" % (stx["unknown"],)))
    # 17j. ЗАПИСАННЫЙ ЖИВОЙ ПРОМАХ, ради которого всё это и делается. Заметка 10.08 07:36
    # (reports/2026-08-10/expect-o3-7a209f7.md, строка 11) сказала владельцу ДОСЛОВНО:
    #   «не знаю, дошёл ли коммит до прода · … · проверить не могу: blind_readers_baseline.json
    #    → на диске лежит не то, что в origin/main · это НЕ «дошло» и НЕ «не дошло»»
    # — а правдой было «не дошёл»: секция (4) этого же сьюта доказывает, что у демона не было
    # scan_result.py. Один грязный ФАЙЛ ДАННЫХ подменил ответ о ЧУЖОМ файле.
    # Числа ниже — ДОСЛОВНО из блока «Сырые факты снимка» того же артефакта: старты юнитов
    # 1786349336.12 и 1786352985.87, момент 1786357206.23, mtime спорного файла 1786356872.34.
    DIRTY1 = "blind_readers_baseline.json"
    snap = facts([C_SCAN], now=1786357206.23, daemon=1786349336.12, splinter=1786352985.87,
                 dirty=(DIRTY1,), mtimes={DIRTY1: 1786356872.3369622,
                                          "blind_readers.py": 1786191664.102177,
                                          "scan_result.py": 1786191547.3299513})
    was = E.delivery_state(C_SCAN, snap)
    res.append(ok(was["state"] == E.UNKNOWN
                  and [p for p, _w in was["unknown"]] == [DIRTY1] and not was["missing"],
                  "(17j) дословный промах 10.08 воспроизведён прежним правилом: %s, «%s»"
                  % (was["state"], was["unknown"][0][0])))
    snap["delivery"]["blobs"] = {DIRTY1: {"7a209f7":
                                          "185ab8d4230a9ed490bfe76aad56af48aa8e8ad8"}}
    snap["delivery"]["disk"] = {DIRTY1: WIP_BLOB}
    st_now = E.delivery_state(C_SCAN, snap)
    res.append(ok(st_now["state"] == E.DELIVERED and not st_now["unknown"],
                  "(17j) новым — тот же коммит и те же факты дают ОТВЕТ: %s" % st_now["state"]))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(17) вердикт по содержимому")] * 14


# ═══ (18) РУКИ: ДВА ХЕША — ФАКТ, А НЕ ДОГАДКА; ЧИСТОЕ ДЕРЕВО НЕ ПЛАТИТ НИЧЕГО ═══
print("\n(18) руки: хеш блоба совпадает с git, а на чистом дереве команда не зовётся вовсе")
try:
    import subprocess as SP
    import expectations_run as ER

    mine = ER.blob_sha1(os.path.join(REPO, "expectations.py"))
    his = SP.run(["git", "hash-object", "expectations.py"], cwd=REPO,
                 capture_output=True, text=True).stdout.strip()
    res.append(ok(mine and mine == his,
                  "(18a) свой хеш блоба == git hash-object на живом файле: %s" % (mine or "")[:12]))

    calls = []
    real = ER._git
    ER._git = lambda a: (calls.append(a), real(a))[1]
    try:
        res.append(ok(ER.commit_blobs("2026-08-13 00:00:00 +0000", []) == {} and not calls,
                      "(18b) спорных файлов нет → ни одной команды git: вызовов %d" % len(calls)))
        got = ER.commit_blobs("2026-08-13 00:00:00 +0000", ["invariants_check.py"])
    finally:
        ER._git = real
    res.append(ok(got.get("invariants_check.py", {}).get("baf5d30") == HOT11[0][2],
                  "(18c) на живом репозитории блоб коммита прочитан верно: %s"
                  % str(got.get("invariants_check.py", {}).get("baf5d30"))[:12]))
    res.append(ok(all(len(v) == 40 for m in got.values() for v in m.values()),
                  "(18c) и все хеши полные, а не сокращённые"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(18) руки: хеши")] * 4

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
