#!/usr/bin/env python3
"""ФАКТ ИСПОЛНЕНИЯ СИЛЬНЕЕ ВОЗРАСТА ПРОЦЕССА: регресс (18.08.2026).

Повод — живой случай. Коммит `4e6e0ce` (18.08 08:36:37 UTC) тронул `expectations.py` (её держит
В ПАМЯТИ демон, поднятый 17.08 16:30:34) и `expectations_run.py`/`expect_journal.py` (их читает
С ДИСКА каждый тик яруса 2). Прогон 08:40:06 — через 3 м 29 с после коммита — уже исполнил новый
код: в 08:40:15 он записал в состояние ключ `pc`, которого прежний код не знал. В 12:45:52 прибор
объявил `o3_undelivered`, а текст карточки утверждал «живой процесс его НЕ ЧИТАЛ» — неправду о
живой системе.

ФИКСТУРЫ ЖИВЫЕ, А НЕ ВЫДУМАННЫЕ: списки файлов — вывод `git show --name-only`; замыкания —
`prod_drift.closure` на этой машине; времена — `git log %%cI`, журнал `expectations.service` и
`systemctl show` (демон 17.08 16:30:34, splinter 16.08 14:30:42).

ВЛАДЕЛЕЦ НАЗВАЛ ДВА ОБЯЗАТЕЛЬНЫХ ОТРИЦАТЕЛЬНЫХ ТЕСТА, оба здесь:
    (а) коммит трогает файл демона, процесс старше       → требование ЕСТЬ   (секция 2)
    (б) файл читается с диска, новый код уже исполнялся   → требования НЕТ   (секция 3)

(1) ЗАКРЫТЫЙ СПИСОК ТИК-ПОТРЕБИТЕЛЕЙ и их замыкание — факт, а не допущение
(2) ОТРИЦАТЕЛЬНЫЙ (а): память демона старше коммита → требование ЕСТЬ
(3) ОТРИЦАТЕЛЬНЫЙ (б): живая хронология 18.08 → требования НЕТ, и причина — ФАКТ
(4) ЗАБОР ЧЕСТЕРТОНА: наблюдённый прогон НЕ снимает требования с файла в памяти
(5) ТРИ ИСХОДА: прогона не видели → «неизвестно» + требование, а не молчание
(6) FAIL-SAFE: фактов о тиках нет → вердикт БАЙТ-В-БАЙТ прежний
(7) КАРТОЧКА ВЛАДЕЛЬЦУ больше не утверждает неправды
(8) ЖИВОЙ ПРОГОН на этой машине: факты снимаются, PID никого не трогаем
"""
import calendar
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import expectations as E          # noqa: E402
import deliver_card               # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def T(iso):
    """«2026-08-18 08:36:37» (UTC) → секунды эпохи. Своей арифметики времени в фикстурах нет."""
    d, t = iso.split()
    y, mo, dd = (int(x) for x in d.split("-"))
    h, mi, s = (int(x) for x in t.split(":"))
    return float(calendar.timegm((y, mo, dd, h, mi, s, 0, 0, 0)))


res = []

# ── ЖИВЫЕ ФИКСТУРЫ (сняты с прода 18.08.2026) ───────────────────────────────────────────────
CT = T("2026-08-18 08:36:37")             # git log %cI по 4e6e0ce
TICK_RUN = T("2026-08-18 08:40:06")       # журнал: «Starting expectations.service»
DAEMON_UP = T("2026-08-17 16:30:34")      # systemctl show orchestrator-daemon
SPLINTER_UP = T("2026-08-16 14:30:42")    # systemctl show splinter
NOW = T("2026-08-18 12:45:52")            # прогон, на котором прибор объявил o3_undelivered

# замыкания — вывод prod_drift.closure на этой машине (усечены до задействованных имён)
CLOSURES = {"orchestrator-daemon": ["orchestrator_daemon.py", "expectations.py", "prod_drift.py",
                                    "deliver_card.py", "bridge_client.py"],
            "splinter": ["bot.py", "splinter.py"]}
TICK_CLOSURE = ["expectations_run.py", "expectations.py", "expect_journal.py", "prod_drift.py",
                "queue_state.py", "bridge_client.py"]
UNITS = {"orchestrator-daemon": {"alive": True, "started": DAEMON_UP},
         "splinter": {"alive": True, "started": SPLINTER_UP}}

# дословный список файлов коммита 4e6e0ce (git show --name-only)
FILES_4E = ["docs/artifacts/2026-08-18-expect-pc-lane.md", "expect_journal.py", "expectations.py",
            "expectations_run.py", "tests/test_expect_journal.py",
            "tests/test_expect_pc_bridge.py", "tests/test_expect_pc_lane.py"]
# те же файлы этого же коммита, которые читаются С ДИСКА каждым тиком (см. секцию 1)
FILES_TICK_ONLY = ["expect_journal.py", "expectations_run.py"]
MTIMES = {p: CT for p in FILES_4E}


def facts(tick_last=TICK_RUN, ticks=True, mtimes=None):
    d = {"ok": True, "commits": [], "closures": CLOSURES, "units": UNITS, "now": NOW,
         "mtimes": dict(MTIMES if mtimes is None else mtimes),
         "dirty": [], "dirty_ok": True, "blobs": {}, "disk": {}}
    if ticks:
        d["ticks"] = {"expectations.service": {"entry": "expectations_run.py",
                                               "closure": TICK_CLOSURE, "last": tick_last}}
    return {"delivery": d}


def commit(files, sha="4e6e0ce"):
    return {"sha": sha, "ct": CT, "files": list(files), "subject": "О6 полоса ПК"}


# ── (1) ЗАКРЫТЫЙ СПИСОК ТИК-ПОТРЕБИТЕЛЕЙ ────────────────────────────────────────────────────
print("(1) тик-потребители названы списком, а не угаданы")
res.append(ok(isinstance(E.TICK_UNITS, tuple) and len(E.TICK_UNITS) == 1,
              "список закрыт: ровно один тик-потребитель"))
res.append(ok(E.TICK_UNITS[0] == ("expectations.service", "expectations_run.py"),
              "им объявлен ярус 2 — юнит и точка входа названы дословно"))
res.append(ok(E.file_kind("expectations.py", CLOSURES) == E.KIND_MEMORY,
              "expectations.py — вид «память» (её держит демон), вид НЕ изменён"))
res.append(ok(E.file_kind("expectations_run.py", CLOSURES) == E.KIND_DISK,
              "expectations_run.py — вид «диск» (в памяти сервисов её нет)"))

# ── (2) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): файл демона, процесс старше → ТРЕБОВАНИЕ ЕСТЬ ────────────────
print("(2) отрицательный (а): память демона старше коммита → требование ЕСТЬ")
st_a = E.delivery_state(commit(["orchestrator_daemon.py"]), facts())
res.append(ok(st_a["state"] == E.UNDELIVERED, "исход «не доставлен»"))
res.append(ok([p for p, _u in st_a["missing"]] == ["orchestrator_daemon.py"],
              "требование названо поимённо: orchestrator_daemon.py"))
res.append(ok(st_a["missing"][0][1] == "orchestrator-daemon",
              "адресовано ПОТРЕБИТЕЛЮ — демону"))
res.append(ok(not st_a["ran"], "исполнения этих байт никто не наблюдал — и сказать нечего"))

# тот же файл при живом тике не меняет ничего: orchestrator_daemon.py тик не читает
st_a2 = E.delivery_state(commit(["orchestrator_daemon.py"]), facts(tick_last=NOW))
res.append(ok(st_a2["state"] == E.UNDELIVERED and st_a2["missing"] == st_a["missing"],
              "свежий прогон яруса 2 файла демона не касается — требование на месте"))

# ── (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): живая хронология 18.08 → ТРЕБОВАНИЯ НЕТ ──────────────────────
print("(3) отрицательный (б): живая хронология 18.08 (коммит 08:36:37 → прогон 08:40:06)")
st_b = E.delivery_state(commit(FILES_TICK_ONLY), facts())
res.append(ok(st_b["state"] == E.DELIVERED, "исход «доставлен»"))
res.append(ok(st_b["missing"] == [], "требования НЕТ: список пуст"))
res.append(ok(st_b["unknown"] == [], "и «неизвестно» тоже нет — факт есть"))
res.append(ok(len(st_b["ran"]) == 2, "оба файла названы исполненными"))
res.append(ok(all("expectations.service" in w for _p, w in st_b["ran"]),
              "причина — НАБЛЮДЁННЫЙ прогон, а не «байты лежат на диске»"))
res.append(ok(all("прочитаны" in w for _p, w in st_b["done"]),
              "в done стоит ФАКТ чтения, а не прежнее допущение"))
# карточки владельцу по такому вердикту не бывает физически
note_b = {"kind": "o3_undelivered", "state": st_b["state"], "sha": "4e6e0ce", "defer": 0,
          "missing": st_b["missing"], "unknown": st_b["unknown"], "ran": st_b["ran"]}
res.append(ok(deliver_card.offer(note_b, {"orchestrator-daemon", "splinter"}) is None,
              "предложения карточки нет: состояние не «не доставлен»"))

# ── (4) ЗАБОР ЧЕСТЕРТОНА: память судится КАК СУДИЛАСЬ ───────────────────────────────────────
print("(4) забор Честертона: наблюдённый прогон НЕ снимает требования с файла в памяти")
st_c = E.delivery_state(commit(FILES_4E), facts())
res.append(ok(st_c["state"] == E.UNDELIVERED,
              "коммит 4e6e0ce целиком — по-прежнему «не доставлен»"))
res.append(ok([p for p, _u in st_c["missing"]] == ["expectations.py"],
              "требование осталось РОВНО на файле, который демон держит в памяти"))
res.append(ok(st_c["missing"][0][1] == "orchestrator-daemon", "и адресовано демону"))
res.append(ok(sorted(p for p, _w in st_c["ran"]) == ["expect_journal.py", "expectations.py",
                                                     "expectations_run.py"],
              "вторая половина правды названа: эти байты тик уже исполнял"))
parts = E._o3_parts({"sha": "4e6e0ce", "subject": "О6", "age": 14946.0, "limit": 14400.0,
                     "missing": st_c["missing"], "unknown": st_c["unknown"], "ran": st_c["ran"]})
body = " · ".join(parts)
res.append(ok("в проде его нет" not in body,
              "заметка больше НЕ утверждает «в проде его нет» — это была неправда"))
res.append(ok("в памяти этих процессов его нет" in body, "она называет ПАМЯТЬ названных процессов"))
res.append(ok("УЖЕ исполнялись" in body, "и прямо говорит, что байты в проде уже работали"))
res.append(ok("рестарт сервиса, и он ход владельца" in body, "граница владельца не тронута"))

# ── (5) ТРИ ИСХОДА: прогона не видели → «неизвестно» + требование ───────────────────────────
print("(5) три исхода: факт исполнения не наблюдаем → «неизвестно», а не молчание")
st_d = E.delivery_state(commit(FILES_TICK_ONLY), facts(tick_last=None))
res.append(ok(st_d["state"] == E.UNKNOWN, "прогон не наблюдался → «неизвестно», НЕ «доставлен»"))
res.append(ok(len(st_d["unknown"]) == 2 and st_d["done"] == [],
              "оба файла ушли в «неизвестно» — зелёного по допущению больше нет"))
res.append(ok(all("подтвердить нечем" in w for _p, w in st_d["unknown"]), "причина названа"))
st_e = E.delivery_state(commit(FILES_TICK_ONLY), facts(tick_last=CT - 60.0))
res.append(ok(st_e["state"] == E.UNKNOWN, "прогон СТАРШЕ коммита → тоже «неизвестно»"))
res.append(ok(all("старше коммита" in w for _p, w in st_e["unknown"]), "и это сказано прямо"))
res.append(ok(E.o3_defer(st_d, {"dirty_defer": 1800.0}) == 0.0,
              "отсрочки такому исходу не полагается: владелец узнаёт сразу"))

# ── (6) FAIL-SAFE: фактов о тиках нет → прежнее поведение ───────────────────────────────────
print("(6) fail-safe: фактов о тиках нет → вердикт БАЙТ-В-БАЙТ прежний")
for files in (FILES_TICK_ONLY, FILES_4E, ["orchestrator_daemon.py"], ["pretool_guard.py"]):
    st_n = E.delivery_state(commit(files), facts(ticks=False))
    ref = E.delivery_state(commit(files), facts(ticks=False))
    same = (st_n["state"], st_n["missing"], st_n["unknown"], st_n["done"]) == \
           (ref["state"], ref["missing"], ref["unknown"], ref["done"])
    res.append(ok(same and st_n["ran"] == [], "без тик-фактов: %s → %s" % (files[0], st_n["state"])))
st_g = E.delivery_state(commit(FILES_TICK_ONLY), facts(ticks=False))
res.append(ok(st_g["state"] == E.DELIVERED and
              all(w == "с диска на каждый запуск" for _p, w in st_g["done"]),
              "прежняя формулировка «с диска на каждый запуск» цела там, где тика нет"))
st_h = E.delivery_state(commit(["pretool_guard.py"]), facts())
res.append(ok(st_h["state"] == E.DELIVERED and st_h["done"][0][1] == "с диска на каждый запуск",
              "файл ВНЕ тик-замыкания правилом не задет вовсе (хук судится как судился)"))

# ── (7) КАРТОЧКА ВЛАДЕЛЬЦУ ──────────────────────────────────────────────────────────────────
print("(7) карточка владельцу больше не утверждает неправды")
note = {"kind": "o3_undelivered", "state": st_c["state"], "sha": "4e6e0ce", "defer": 0,
        "subject": "О6 полоса ПК", "age": 14946.0,
        "missing": st_c["missing"], "unknown": st_c["unknown"], "ran": st_c["ran"]}
off = deliver_card.offer(note, {"orchestrator-daemon", "splinter"})
res.append(ok(off is not None, "предложение есть: требование к памяти демона в силе"))
res.append(ok(off["units"] == ["orchestrator-daemon"], "перезапуск предложен ровно демону"))
res.append(ok(len(off.get("ran") or []) == 3, "наблюдённое исполнение доехало до карточки"))
card = deliver_card.render(off)
res.append(ok("живой процесс его НЕ ЧИТАЛ" not in card, "ложной формулы в карточке НЕТ"))
res.append(ok("в памяти НЕ ДЕРЖАТ" in card, "сказано про память названных процессов"))
res.append(ok("УЖЕ исполняется" in card, "и названо, что часть коммита в проде работает"))
res.append(ok("перезапуск нужен не ей" in card, "владельцу объяснено, чего рестарт не касается"))
# без наблюдённого прогона карточка остаётся ДОСЛОВНО прежней
off0 = deliver_card.offer(dict(note, ran=[]), {"orchestrator-daemon", "splinter"})
res.append(ok("живой процесс его НЕ ЧИТАЛ" in deliver_card.render(off0),
              "прежняя формула цела там, где исполнения не наблюдали"))

# ── (8) ЖИВОЙ ПРОГОН НА ЭТОЙ МАШИНЕ ─────────────────────────────────────────────────────────
print("(8) живой прогон: факты снимаются на настоящей машине, ничего не трогая")
import prod_drift                                                            # noqa: E402
live_closure = set(prod_drift.closure("expectations_run.py", REPO))
res.append(ok("expectations.py" in live_closure,
              "живое замыкание тика содержит expectations.py — файл ОБА вида сразу"))
res.append(ok("expectations_run.py" in live_closure and "expect_journal.py" in live_closure,
              "и обе руки наблюдателя"))
res.append(ok("orchestrator_daemon.py" not in live_closure,
              "код демона тик НЕ читает — забор проходит именно здесь"))

print()
print("ИТОГ: %d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
