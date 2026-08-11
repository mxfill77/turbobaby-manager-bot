# -*- coding: utf-8 -*-
"""ПОРОГ ВЕСА СЕРИИ И ЕГО ЗАМОК (11.08.2026).

ЧТО ЗДЕСЬ СУДИТСЯ — три вещи, и все три названы рамкой §8г:

  (1) ЗАМОК: вес считается ПО ОПЕРАЦИИ, а не по наличию хеша в тексте отчёта. Иначе прибор мерит
      ДИСЦИПЛИНУ НАЗЫВАНИЯ, о чём замер 11.08 предупредил прямо, а живой корпус доказал делом:
      шести цепочкам зачлись ЧУЖИЕ коммиты, процитированные в их отчётах (361 назвала девять
      хешей чужих цепочек), а шесть сделавших работу молча не получили своего веса.
  (2) ЧИСЛА порога: 0.30 доли и 10 наблюдаемых цепочек знаменателя — оба выведены из замера
      (`docs/artifacts/2026-08-11-series-weight-threshold.md`), а не выбраны.
  (3) ТРЕТИЙ ИСХОД: серия, чей вес НЕ НАБЛЮДАЕМ (полоса pc — чужой репозиторий), получает
      «неизвестно», а НЕ «нет». Порогом карать за чужой репозиторий нельзя.

ГРАНИЦЫ, которые тест стережёт отдельно: критерий выхода из фазы (SERIES_TARGET=30) и сорта
вмешательства не тронуты; вес по-прежнему даёт И свой перезапуск сервиса; гард не участвует.

Запуск: venv/bin/python3 tests/test_chain_series_weight.py   (в гейте)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ["CHAIN_SERIES"] = "0"          # руки демона здесь не трогаем: судим решение и реплей

import chain_series as CS                                                    # noqa: E402
import chain_series_report as CSR                                            # noqa: E402

res = []


def ok(cond, name):
    print(("  ✅ " if cond else "  ❌ ") + name)
    return bool(cond)


# ────────────────────────────────────────────────────────────────────────────────────────────
print("(1) ЧИСЛА ПОРОГА — из замера, не из красоты")
res.append(ok(CS.WEIGHT_MIN_SHARE == 0.30,
              "(1) доля веса 30 %% = живое дно 35.0 %% минус ОДНА цепочка его окна (7 из 20 → "
              "шаг 5.0 п.п.); стоит %.2f" % CS.WEIGHT_MIN_SHARE))
res.append(ok(CS.WEIGHT_MIN_KNOWN == 10,
              "(1) знаменатель ≥10 наблюдаемых: ниже десяти дно обваливается до 0 %%, а ≥24 "
              "достижим лишь в 10 %% окон; стоит %d" % CS.WEIGHT_MIN_KNOWN))
res.append(ok(CS.SERIES_TARGET == 30,
              "(1) КРИТЕРИЙ ВЫХОДА ИЗ ФАЗЫ НЕ ТРОНУТ — 30 цепочек, как в рамке"))
res.append(ok(CS.SORTS == (CS.NOISE, CS.WILL, CS.MANUAL, CS.UNKNOWN),
              "(1) сорта вмешательства не тронуты"))
res.append(ok(0.0 < CS.WEIGHT_MIN_SHARE < 0.35,
              "(1) порог строго НИЖЕ живого дна 35.0 % — судит подлог, а не работу"))


def chain(root, commits=(), restarts=0, known=True, lane="vps", statuses=("done",), cards=()):
    return {"root": root, "lane": lane, "created": "2026-08-01T00:00:00",
            "closed_at": "2026-08-01T01:00:00", "statuses": list(statuses),
            "cards": [dict(c) for c in cards], "refusals": [],
            "weight": {"commits": list(commits), "restarts": restarts, "known": known}}


def run_of(n, weighty, known=True, lane="vps"):
    """n чистых цепочек подряд, из них `weighty` с весом."""
    return [CS.chain_verdict(chain(i, commits=(["c%05d" % i] if i <= weighty else []),
                                   known=known, lane=lane)) for i in range(1, n + 1)]


print("(2) ТРИ ИСХОДА ЗАЧЁТНОСТИ — «неизвестно» отдельным словом")
st_yes = CS.series(run_of(30, 12))              # 12 из 30 = 40 % ≥ 30 %
res.append(ok(st_yes["qualified"] == CS.QUAL_YES,
              "(2) длина 30 и вес 40 %% → зачётная (%s)" % st_yes["qualified_why"][:60]))
st_no = CS.series(run_of(30, 6))                # 6 из 30 = 20 % < 30 %
res.append(ok(st_no["qualified"] == CS.QUAL_NO,
              "(2) длина 30, вес 20 % → НЕТ: длину набрали цепочками без операций"))
st_short = CS.series(run_of(29, 29))
res.append(ok(st_short["qualified"] == CS.QUAL_NO and "длины нет" in st_short["qualified_why"],
              "(2) длины нет → «нет» (длина наблюдаема всегда, это ФАКТ, а не незнание)"))
st_pc = CS.series(run_of(30, 0, known=False, lane="pc"))
res.append(ok(st_pc["qualified"] == CS.QUAL_UNKNOWN,
              "(2) 30 цепочек полосы pc → НЕИЗВЕСТНО, а не «нет»: карать за чужой репозиторий "
              "значит наказать не за слабую работу"))
mix = run_of(30, 0, known=False, lane="pc")[:21] + run_of(9, 9)[:9]
st_thin = CS.series(mix)
res.append(ok(st_thin["qualified"] == CS.QUAL_UNKNOWN and st_thin["current_known"] == 9,
              "(2) знаменатель 9 (<10) → НЕИЗВЕСТНО: на тонкой почве порог не объявляется"))
mix10 = run_of(30, 0, known=False, lane="pc")[:20] + run_of(10, 10)[:10]
res.append(ok(CS.series(mix10)["qualified"] == CS.QUAL_YES,
              "(2) знаменатель ровно 10 и вес 100 % → судим и зачтено (граница включительна)"))
res.append(ok(CS.QUAL_UNKNOWN not in (True, False) and isinstance(CS.QUAL_UNKNOWN, str),
              "(2) исход НЕ булев: «неизвестно» нельзя молча прочитать как «нет»"))
res.append(ok("неизвестно" in CS.render(CS.series(run_of(30, 0, known=False, lane="pc"))),
              "(2) строка журнала называет исход словом, а не молчит о нём"))

print("(3) ВЕС ЦЕПОЧКИ — что им является")
res.append(ok(CS.chain_verdict(chain(1, commits=["6e525d6"]))["weight"],
              "(3) коммит origin/main в окне исполнения = вес"))
res.append(ok(CS.chain_verdict(chain(1, restarts=1))["weight"],
              "(3) свой перезапуск сервиса = вес (граница не тронута)"))
res.append(ok(not CS.chain_verdict(chain(1))["weight"],
              "(3) цепочка без операции веса не даёт"))
pc = CS.chain_verdict(chain(1, commits=["6e525d6"], known=False, lane="pc"))
res.append(ok(pc["weight_known"] is False and pc["weight"] is False,
              "(3) вес полосы pc НЕ НАБЛЮДАЕМ — третье состояние, а не нуль"))

# ────────────────────────────────────────────────────────────────────────────────────────────
# ЗАМОК. Ниже — реплей на ДОСЛОВНОЙ фактуре живого корпуса (снимок очереди 11.08.2026):
# цепочка 361 процитировала в отчёте девять ЧУЖИХ хешей, своих коммитов у неё нет; цепочка 130
# сделала коммит и хеша не назвала. Оба случая прибор-хеш судил НЕВЕРНО в разные стороны.
C361 = ("итог ревизии: перечислены фиксы 05c110b, 20ebbc1, 40c8425, 53ce1a9, 9906598, 9da54b8, "
        "a77c14e, af55ac7, baf1c60 — все они живут в проде, замечаний нет")
C130 = "готово, гейт зелёный 171, откат прописан"          # хеша в тексте НЕТ ВООБЩЕ
SHA_OWN, SHA_ALIEN = "1c238950" + "0" * 32, "40c84250" + "0" * 32


def replay(text, own_window=True, sha=SHA_OWN, at="2026-08-05T12:30:00", lane="vps"):
    """Один прогон реплея: одна запись очереди, один коммит в origin/main, окно исполнения."""
    entries = [{"id": 700, "lane": lane, "status": "done", "task_text": "ultrathink ЦЕЛЬ: тест",
                "created": "2026-08-05T12:00:00.000Z", "updated": "2026-08-05T13:00:00.000Z",
                "result": text}]
    windows = {700: ("2026-08-05T12:10:00", "2026-08-05T12:50:00")} if own_window else {}
    verdicts, chains, order, _st = CSR.build(entries, [], {sha: at}, windows, {})
    return verdicts[0], chains[order[0]]["weight"]["commits"]


# ЧУЖОЙ КОММИТ КЛАДЁТСЯ В ЗАЗОР МЕЖДУ ДВУМЯ ОКНАМИ, и это не придирка к фикстуре, а СУТЬ дефекта:
# прежний прибор мерил окно ОЧЕРЕДИ (12:00–13:00 — от постановки до терминала), а работа шла в
# окне ИСПОЛНЕНИЯ (12:10–12:50). В зазоре живёт чужая работа: у 361 так и вышло — девять коммитов
# соседних цепочек попали в её длинное очередное окно и стали её «весом».
v_quote, c_quote = replay(C361, own_window=True, sha=SHA_ALIEN, at="2026-08-05T12:55:00")
res.append(ok(not v_quote["weight"] and c_quote == [],
              "(4) ЗАМОК: девять ЧУЖИХ хешей в отчёте веса НЕ дают — коммит вне окна ИСПОЛНЕНИЯ, "
              "хотя внутри окна очереди (так и было у 361)"))
v_silent, c_silent = replay(C130, own_window=True)
res.append(ok(v_silent["weight"] and c_silent == ["1c23895"],
              "(4) ЗАМОК: работа в окне засчитана, хотя отчёт хеша НЕ НАЗВАЛ ВОВСЕ"))

print("(4) ЗАМОК: ТЕКСТ ОТЧЁТА НА ВЕС НЕ ВЛИЯЕТ НИ В ОДНУ СТОРОНУ")
same = [replay(t)[0]["weight"] for t in (
    "готово",                                              # молчит
    "готово, commit 1c23895 в origin/main",                # называет СВОЙ хеш
    "готово, проверил чужой фикс 40c8425 и 9906598",       # называет ЧУЖИЕ
    C361, C130,
)]
res.append(ok(len(set(same)) == 1 and same[0] is True,
              "(4) при ОДНИХ И ТЕХ ЖЕ фактах мира пять РАЗНЫХ текстов дают один вес (%s)" % same))
none = [replay(t, own_window=False)[0]["weight"] for t in (
    "готово", "готово, commit 1c23895 в origin/main", C361)]
res.append(ok(not any(none),
              "(4) без окна исполнения не помогает НИКАКОЙ текст — назвать себе вес нельзя (%s)"
              % none))
res.append(ok(not replay("готово", sha=SHA_OWN, at="2026-08-05T12:55:00")[0]["weight"],
              "(4) коммит ПОСЛЕ конца окна не приписывается: хвоста у веса нет намеренно"))
res.append(ok(not replay("готово", sha=SHA_OWN, at="2026-08-05T12:05:00")[0]["weight"],
              "(4) коммит ДО начала окна не приписывается (задача ещё стояла в new)"))
res.append(ok(not replay("готово", lane="pc")[0]["weight_known"],
              "(4) полоса pc: окно чужое, вес не наблюдаем — приписки не происходит"))

print("(5) ЗАМОК СТРУКТУРНЫЙ — прибору нечем прочитать хеш из текста")
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "chain_series_report.py"), encoding="utf-8").read()
body = src.split("def build(")[1].split("\ndef ")[0]
res.append(ok(not re.search(r"0-9a-f\]\{\d", src),
              "(5) в модуле реплея НЕТ образца хеша — вернуть его значит вернуть прибор "
              "дисциплины называния"))
res.append(ok('weight' in body and 'result' not in body.split("--- вес")[1].split("--- старты")[0],
              "(5) в куске, где считается вес, текст терминала не упоминается вовсе"))
dsrc = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "orchestrator_daemon.py"), encoding="utf-8").read()
dfun = dsrc.split("def _series_commits(")[1].split("\ndef ")[0]
res.append(ok(dfun.startswith("lo, hi)"),
              "(5) у живого счёта тот же замок: _series_commits берёт ОКНО, а не текст отчёта"))
res.append(ok("result" not in dfun and "findall" not in dfun,
              "(5) в теле _series_commits нет ни отчёта, ни поиска по нему"))

print("(6) ПОРОГ ОТЧИТЫВАЕТСЯ ПЕРЕД ЖИВОЙ РАБОТОЙ (окно = сама единица зачёта)")
# 60 чистых цепочек: первые 30 — вес у 12 (40 %), дальше вес у каждой второй.
seq = [CS.chain_verdict(chain(i, commits=(["c%05d" % i] if (i <= 12 or i % 2 == 0) else [])))
       for i in range(1, 61)]
qw, thin = CS.qualify_windows(seq)
res.append(ok(len(qw) == 31 and thin == 0 and min(qw) >= 0.40,
              "(6) окна считаются по ЧИСТЫМ цепочкам подряд — той единице, к которой применён "
              "порог (окон %d, тонких %d, min %.2f)" % (len(qw), thin, min(qw) if qw else -1)))
blind_seq = [CS.chain_verdict(chain(i, known=False, lane="pc")) for i in range(1, 41)]
qwb, thinb = CS.qualify_windows(blind_seq)
res.append(ok(qwb == [] and thinb == 11,
              "(6) ненаблюдаемые окна НЕ судятся и названы числом (%d), а не зачтены нулём"
              % thinb))

print("(7) ГРАНИЦЫ: чего заход не трогал")
res.append(ok(CS.sort_card([], [], "", "")["sort"] == CS.NOISE
              and CS.sort_card(["service:splinter"], [], "2026-08-01T00:00:00", "")["sort"]
              == CS.WILL, "(7) сорт вмешательства судится как прежде"))
res.append(ok(CS.refusal("failed", "причина=run_timeout") == "зависание"
              and CS.refusal("done", "причина=run_timeout") == "",
              "(7) необъяснённый отказ судится как прежде"))
res.append(ok(len([n for n in dir(CS) if n == "WEIGHT_MIN_SHARE"]) == 1
              and CS.weight_windows([]) == [],
              "(7) прежняя `weight_windows` жива — старая ось распределения не убрана"))

print("\nИТОГО: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
