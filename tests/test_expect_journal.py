#!/usr/bin/env python3
"""НАБЛЮДЕНИЕ УХОДИТ В МОЗГ, А НЕ ВЛАДЕЛЬЦУ: регресс (13.08.2026).

Владелец назвал ДВА направления, и оба проверяются здесь сквозь ЖИВЫЕ руки:
    обычное наблюдение   → в ленту НЕ идёт, а в мозг идёт   (секции 5, 6)
    тяжёлое, пережившее отсрочку → идёт владельцу, как шло  (секция 7)

Фикстуры сняты с прода, а не выдуманы: живой образец О5 13.08 (19:26 «174 с при 120», 19:35
«снова укладывается, 11 с», 19:48 «156 с» — три сообщения за 22 минуты о мосте, который встал
сам за 9 минут); эпизод `o3|7e348d4` — дословный коммит 10.08, тронувший `bridge_prod/
ReadFleet.js` и проживший 120 минут; ключи и времена эпизодов — журнал `expectations.timer`.

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение адреса не умеет ни писать, ни отправлять
(2)  ВЕС: инфраструктура — никогда; названные деньги и живые таблицы — всегда
(3)  ВЕС: замок против слепоты — непрочитанный предмет и незнакомый вид идут к владельцу
(4)  АДРЕС: тяжёлое И пережившее — оба условия обязательны
(5)  РУКИ, НАПРАВЛЕНИЕ 1: обычное наблюдение владельцу НЕ уходит
(6)  ОДНА СТРОКА НА ЭПИЗОД, А НЕ НА ТИК
(7)  РУКИ, НАПРАВЛЕНИЕ 2: тяжёлое, пережившее отсрочку, уходит владельцу
(8)  СТРОКА ЖУРНАЛА: имя ожидания, что нарушено, число, начало и конец, UTC
(9)  FAIL-SAFE: не записалось — не потеряно; записалось — второй строки не будет
(10) ОТКАТ EXPECT_TO_BRAIN=0 — прежний путь байт-в-байт
(11) ПОРОГ О5 240 с: живые 156 и 174 тревоги не дают, 251 даёт
(12) ИЗОЛЯЦИЯ: под тестом в боевой мозг не пишется ничего
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"

import expect_journal as J                                            # noqa: E402
import expectations as E                                              # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
NOW = 1786614515.0                       # живой такт 13.08.2026


# ── ЖИВЫЕ ВЕРДИКТЫ (форма — ровно та, что отдают _o5/_o3/_o1/_o4) ──────────────────────────
V_SLOW = {"kind": "o5_bridge_slow", "key": "o5s|1786614515", "dt": 174.0, "limit": 120.0,
          "can_task": False}
V_DAEMON = {"kind": "o2_daemon", "key": "o2d|1786453501|1786608855", "age": 900.0,
            "limit": 600.0, "alive": True, "pid": 270986, "can_task": False}
# ДОСЛОВНЫЙ живой эпизод: коммит 7e348d4 тронул поверхность живых таблиц и прожил 120 минут.
V_FLEET = {"kind": "o3_undelivered", "key": "o3|7e348d4", "sha": "7e348d4",
           "subject": "папка-мост обезврежена как источник выкладки", "age": 20000.0,
           "limit": 14400.0, "missing": [("bridge_prod/ReadFleet.js", "прод")],
           "unknown": [], "can_task": False}
V_CODE = {"kind": "o3_undelivered", "key": "o3|7bcddba", "sha": "7bcddba",
          "subject": "сторож судит продукт, а не PID", "age": 20000.0, "limit": 14400.0,
          "missing": [("orchestrator_daemon.py", "orchestrator-daemon")], "unknown": [],
          "can_task": False}
V_PC = {"kind": "o4_pc_silent", "key": "o4|1786496820", "age": 60000.0, "limit": 57600.0,
        "line": "🛌 ПК СПАЛ 51 м 43 с", "probe": 2.1, "can_task": False}


# ═══════════ (1) ГРАНИЦА УСТРОЙСТВОМ ═══════════
print("\n(1) ГРАНИЦА УСТРОЙСТВОМ: решение адреса не умеет ни писать, ни отправлять")
try:
    import ast
    src = open(os.path.join(REPO, "expect_journal.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imports = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imports.add((n.module or "").split(".")[0])
    res.append(ok(imports == {"datetime"},
                  "(1a) импорт ровно один — datetime (ради метки UTC): %s" % sorted(imports)))
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    res.append(ok(not ({"open", "exec", "eval", "compile", "__import__"} & calls),
                  "(1b) ни open, ни exec, ни __import__: %s" % sorted(calls)))
    attrs = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    # `get`/`join`/`lower` НЕ запрещаем: это словарь и строка, ими модуль и живёт. Запрещены
    # ровно ручки, которыми ходят наружу и пишут.
    res.append(ok(not ({"run", "Popen", "post", "write", "remove", "system", "unlink",
                        "urlopen", "send_feed"} & attrs),
                  "(1c) ни подпроцесса, ни сети, ни записи: %s" % sorted(attrs)))
    # Тот же вопрос задаёт гейт — инвариантом, а не этим тестом; проверяем, что он ЗАРЕГИСТРИРОВАН.
    import invariants_check as IC
    res.append(ok("EXPECT_JOURNAL_PURE" in {n for n, _fn in IC.CHECKS},
                  "(1d) страж чистоты стоит в гейте, а не только в этом файле"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(1) чистота")] * 4


# ═══════════ (2) ВЕС: ЧТО ЛЕГКО, А ЧТО ТЯЖЕЛО ═══════════
print("\n(2) ВЕС: инфраструктура — никогда; названные деньги и живые таблицы — всегда")
h_slow, w_slow = J.heavy(V_SLOW, None, True)
res.append(ok(h_slow is False and "юнит или канал" in w_slow,
              "(2a) О5 (мост) — предмет есть канал: %s" % w_slow))
res.append(ok(J.heavy(V_DAEMON, None, True)[0] is False,
              "(2b) О2 (демон) — предмет есть юнит, денег в нём не бывает"))
h_fleet, w_fleet = J.heavy(V_FLEET, None, True)
res.append(ok(h_fleet is True and "readfleet" in w_fleet.lower(),
              "(2c) ЖИВОЙ 7e348d4: назван файл поверхности живых таблиц → тяжёлое: %s" % w_fleet))
res.append(ok(J.heavy(V_CODE, None, True)[0] is False,
              "(2d) коммит демона денег и живых таблиц не задевает → лёгкое"))
# Операция живых таблиц, названная в тексте застрявшей задачи.
q_rows = [{"id": 7, "from": "Filipp-328-dev", "text": "запиши ТО масла set_fleet_oil для 4724"}]
V_ROW = {"kind": "o1_new_vps", "key": "o1|7|1786600000", "id": 7, "from": "Filipp-328-dev",
         "age": 3000.0, "free": 2400.0, "limit": 1800.0, "can_task": True}
h_row, w_row = J.heavy(V_ROW, {"queue": {"rows": q_rows}}, True)
res.append(ok(h_row is True and "set_fleet_oil" in w_row,
              "(2e) О1: в тексте застрявшей строки названа операция живых таблиц: %s" % w_row))
q_plain = [{"id": 7, "from": "Filipp-328-dev", "text": "почини тест гейта"}]
res.append(ok(J.heavy(V_ROW, {"queue": {"rows": q_plain}}, True)[0] is False,
              "(2f) О1: обычная дев-задача — лёгкое"))
res.append(ok(J.heavy(V_PC, None, True)[0] is False
              and "ЗАМОРОЖЕН" in J.heavy(V_PC, None, True)[1],
              "(2g) О4 при ЗАМОРОЖЕННОМ контуре — лёгкое (тот же довод, что у revizor_route)"))
res.append(ok(J.heavy(V_PC, None, False)[0] is True,
              "(2h) О4 при РАЗМОРОЖЕННОМ контуре — тяжёлое: ветка оживает сама"))


# ═══════════ (3) ЗАМОК ПРОТИВ СЛЕПОТЫ ═══════════
print("\n(3) ЗАМОК: непрочитанный предмет и незнакомый вид идут к владельцу")
h_noread, w_noread = J.heavy(V_ROW, {"queue": {}}, True)
res.append(ok(h_noread is True and "не прочитан" in w_noread,
              "(3a) снимка очереди нет → предмет не прочитан → ТЯЖЁЛОЕ: %s" % w_noread))
res.append(ok(J.heavy(V_ROW, {"queue": {"rows": []}}, True)[0] is True,
              "(3b) строка ушла из снимка → судить нечем → ТЯЖЁЛОЕ"))
h_new, w_new = J.heavy({"kind": "o6_money_drift", "key": "o6|1"}, None, True)
res.append(ok(h_new is True and "не известен" in w_new,
              "(3c) ВИД, которого правило не знает (появится О6) → ТЯЖЁЛОЕ: %s" % w_new))
res.append(ok(J.heavy(None, None, True)[0] is True and J.heavy({}, None, True)[0] is True,
              "(3d) мусор вместо вердикта → ТЯЖЁЛОЕ (сомнение в сторону владельца)"))
# Ветка ПК в `heavy` одна на два вида: и «следа нет», и «взяла и молчит» — наблюдения о МАШИНЕ
# ПК, а вес у неё один (см. `expect_journal.heavy`). Поэтому оба перечислены здесь рядом.
# У О7 (18.08.2026) СВОИ ветки, и веса у них РАЗНЫЕ намеренно: «ребёнок не жив» называет сам
# клиентский процесс (тяжёлое), «строки о детях нет» — отсутствие сведений (лёгкое).
PC_KINDS = {"o4_pc_silent", "o6_pc_task", "o7_child_down", "o7_pulse_lost"}
res.append(ok(set(J.INFRA_KINDS) | set(J.NAMED_KINDS) | PC_KINDS == set(E.KINDS),
              "(3e) все сегодняшние виды названы явно — «неизвестный вид» это про БУДУЩИЕ"))
res.append(ok(J.heavy({"kind": "o7_child_down", "child": "moderation_bot"}, None, True)[0] is True
              and J.heavy({"kind": "o7_pulse_lost"}, None, True)[0] is False,
              "(3e) …и оба веса О7 названы ЯВНО, а не достались умолчанием"))


# ═══════════ (4) АДРЕС: ОБА УСЛОВИЯ ОБЯЗАТЕЛЬНЫ ═══════════
print("\n(4) АДРЕС: тяжёлое И пережившее отсрочку — оба условия обязательны")
D = 3600.0
res.append(ok(J.address(V_FLEET, None, 0.0, D, True)[0] == J.BRAIN,
              "(4a) тяжёлое, но только что найденное → мозг (это и есть шум живого образца)"))
res.append(ok(J.address(V_FLEET, None, D + 1, D, True)[0] == J.BRAIN_AND_OWNER,
              "(4b) тяжёлое, пережившее отсрочку → мозг+владелец"))
res.append(ok(J.address(V_SLOW, None, D * 10, D, True)[0] == J.BRAIN,
              "(4c) лёгкое, хоть и очень долгое → мозг: владельцу тут нечего решать"))
res.append(ok(J.address(V_FLEET, None, D, D, True)[0] == J.BRAIN_AND_OWNER,
              "(4d) ровно на границе отсрочки — уже пережило"))


# ═══════════ РУКИ: живой прогон с подменённым каналом ═══════════
import expectations_run as ER                                          # noqa: E402


def drive(ticks, verdicts_at, closes_at, brain="1", defer_min="60", journal_ok=True,
          note_ok=True, st0=None):
    """Прогнать РУКИ по тактам. Канал подменён, боевой мозг и reports/ не трогаются.

    `st0` — состояние ДО первого такта: им подаётся запись, заведённая ПРЕЖНЕЙ редакцией рук
    (ровно так и родился живой ноль 13.08: эпизод открыт одной редакцией, закрыт другой)."""
    os.environ["EXPECT_TO_BRAIN"] = brain
    os.environ["EXPECT_OWNER_DEFER_MIN"] = defer_min
    box, sent, wrote, outs = {"st": dict(st0 or {})}, [], [], []
    keep = (ER.load_state, ER.save_state, ER.snapshot, ER.send_note, ER.write_proof,
            ER.enqueue_escalation, ER.write_journal, E.verdict, E.closures)
    ER.load_state = lambda: dict(box["st"])
    ER.save_state = lambda s: box.__setitem__("st", dict(s))
    ER.send_note = lambda t: (sent.append(t), note_ok)[1]
    ER.write_journal = lambda t: (wrote.append(t), journal_ok)[1]
    ER.write_proof = lambda v, f, n: ""
    ER.enqueue_escalation = lambda v: 0
    try:
        for i, tnow in enumerate(ticks):
            ER.snapshot = lambda a=None, b=None, c=None: {"now": tnow, "queue": {"ok": False}}
            E.verdict = lambda f, c=None, _i=i: list(verdicts_at.get(_i) or [])
            E.closures = lambda f, c, keys, _i=i: [k for k in keys if k in (closes_at.get(_i) or [])]
            outs.append(ER.run(now=tnow))
    finally:
        (ER.load_state, ER.save_state, ER.snapshot, ER.send_note, ER.write_proof,
         ER.enqueue_escalation, ER.write_journal, E.verdict, E.closures) = keep
        os.environ.pop("EXPECT_TO_BRAIN", None)
        os.environ.pop("EXPECT_OWNER_DEFER_MIN", None)
    return outs, sent, wrote, box["st"]


T = [NOW + i * 600.0 for i in range(8)]      # такты наблюдателя раз в 10 минут

# ═══════════ (5) НАПРАВЛЕНИЕ 1: ОБЫЧНОЕ НАБЛЮДЕНИЕ ВЛАДЕЛЬЦУ НЕ УХОДИТ ═══════════
print("\n(5) РУКИ, НАПРАВЛЕНИЕ 1: обычное наблюдение в ленту НЕ идёт, а в мозг идёт")
try:
    # Живой образец: мост тянет два такта и встаёт сам — ровно те 9 минут из основания.
    outs, sent, wrote, st = drive(T[:3], {0: [V_SLOW], 1: [V_SLOW]}, {2: ["o5s|1786614515"]})
    res.append(ok(sent == [], "(5a) ВЛАДЕЛЬЦУ НЕ УШЛО НИ ОДНОГО СООБЩЕНИЯ: %s" % sent))
    res.append(ok(len(wrote) == 1, "(5b) а в мозг ушла РОВНО одна строка: %d" % len(wrote)))
    res.append(ok(wrote and wrote[0].startswith("ОЖИДАНИЕ О5"),
                  "(5c) строка ищется по теме: «%s…»" % (wrote[0][:46] if wrote else "")))
    res.append(ok(wrote and "длилось 20 мин" in wrote[0],
                  "(5d) и несёт длительность, накопленную по тактам: %s" % (wrote[0][-90:]
                                                                            if wrote else "")))
    res.append(ok(outs[2]["closed"] == [] and outs[2]["journal"] == ["o5s|1786614515"],
                  "(5e) в итоге прогона эпизод числится journal, а не closed: %s" % outs[2]))
    res.append(ok(not (st.get("open") or {}), "(5f) эпизод не завис открытым навсегда"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(5) направление 1")] * 6


# ═══════════ (6) ОДНА СТРОКА НА ЭПИЗОД, А НЕ НА ТИК ═══════════
print("\n(6) ОДНА СТРОКА НА ЭПИЗОД, А НЕ НА ТИК")
try:
    # Пять тактов подряд одно и то же нарушение (это и был живой шум: «состояние не изменилось»).
    outs, sent, wrote, st = drive(T[:6], {i: [V_SLOW] for i in range(5)}, {5: ["o5s|1786614515"]})
    res.append(ok(sent == [], "(6a) владельцу по-прежнему ничего"))
    res.append(ok(len(wrote) == 1,
                  "(6b) пять тактов одного эпизода → ОДНА строка, а не пять: %d" % len(wrote)))
    res.append(ok(wrote and "наблюдений 5" in wrote[0],
                  "(6c) но число наблюдений названо — длительность копилась: %s"
                  % (wrote[0][-80:] if wrote else "")))
    res.append(ok(wrote and "длилось 50 мин" in wrote[0], "(6d) и длительность верна"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(6) одна строка")] * 4


# ═══════════ (7) НАПРАВЛЕНИЕ 2: ТЯЖЁЛОЕ, ПЕРЕЖИВШЕЕ ОТСРОЧКУ, ИДЁТ ВЛАДЕЛЬЦУ ═══════════
print("\n(7) РУКИ, НАПРАВЛЕНИЕ 2: тяжёлое, пережившее отсрочку, уходит владельцу")
try:
    # 7 тактов = 60 минут: ровно отсрочка. Живой эпизод o3|7e348d4 прожил 120 минут.
    outs, sent, wrote, st = drive(T[:8], {i: [V_FLEET] for i in range(8)}, {})
    res.append(ok(all(o["notes"] == [] for o in outs[:6]),
                  "(7a) первые 60 минут владельцу МОЛЧИМ — отсрочка"))
    res.append(ok(outs[6]["notes"] == ["o3|7e348d4"],
                  "(7b) пережило отсрочку → ЗАМЕТКА ВЛАДЕЛЬЦУ: %s" % outs[6]["notes"]))
    res.append(ok(len(sent) == 1 and "не дошёл до прода" in sent[0],
                  "(7c) текст заметки НЕ изменился — менялся адрес, не вердикт"))
    res.append(ok("держал заметку" in sent[0],
                  "(7d) и заметка сама говорит, сколько её держали: %s" % sent[0][-120:]))
    res.append(ok(len(sent) == 1, "(7e) повтора на следующих тактах нет: %d" % len(sent)))
    res.append(ok(sum(1 for w in wrote if "ещё идёт" in w) == 1,
                  "(7f) в мозг ушла строка «держится» — ровно одна, и на 8 тактов не восемь: %s"
                  % [w[-58:] for w in wrote]))
    # ЛЁГКОЕ той же длины владельцу так и не уходит.
    outs2, sent2, _w2, _s2 = drive(T[:8], {i: [V_SLOW] for i in range(8)}, {})
    res.append(ok(sent2 == [],
                  "(7g) ЛЁГКОЕ той же длины (8 тактов) владельцу не уходит НИКОГДА: %s" % sent2))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(7) направление 2")] * 7


# ═══════════ (8) СТРОКА ЖУРНАЛА ═══════════
print("\n(8) СТРОКА ЖУРНАЛА: имя ожидания, что нарушено, число, начало и конец, UTC")
ln = J.line(V_SLOW, "VPS", NOW, NOW + 540, "закрыт", 2, "проба прошла за 11 с")
print("      %s" % ln)
res.append(ok(ln.startswith("ОЖИДАНИЕ О5 · VPS"), "(8a) ищется по теме и называет полосу"))
res.append(ok("мост отвечает дольше отведённого времени" in ln, "(8b) названо, ЧТО нарушено"))
res.append(ok("174" in ln and "120" in ln, "(8c) названо ЧИСЛО: сколько при каком пороге"))
res.append(ok("начало 2026-08-13 " in ln and "конец 2026-08-13 " in ln and "UTC" in ln,
              "(8d) названы начало и конец эпизода, и метка UTC (не Bangkok +7)"))
res.append(ok("длилось 9 мин" in ln, "(8e) и длительность"))
res.append(ok("эпизод o5s|1786614515" in ln, "(8f) ключ эпизода — для сверки с доказательством"))
res.append(ok("проба прошла за 11 с" in ln, "(8g) диагноз закрытия не теряется"))
held_ln = J.line(V_FLEET, "VPS", NOW, NOW + 7200, "держится", 12)
res.append(ok("ещё идёт, уже 2 ч 0 мин" in held_ln and "конец" not in held_ln,
              "(8h) у идущего эпизода конца нет, и он не выдуман: %s" % held_ln[-70:]))
# ЖИВОЙ СЛУЧАЙ 13.08: первый эпизод, закрытый новым кодом, был ЗАВЕДЁН старым — чисел в его
# записи нет вовсе, и строка сказала «опрос очереди 0 с при отведённых 0 с». Ноль здесь ложь.
legacy = J.line({"kind": "o5_bridge_slow", "key": "o5s|1786626993"}, "VPS", NOW, NOW + 1200)
res.append(ok(J.NO_NUMBER in legacy and " 0 с" not in legacy,
              "(8i) ЖИВОЙ 13.08: у легаси-записи нет чисел → сказано ПРЯМО, а не «0 с»: %s"
              % legacy[:150]))
res.append(ok(J._num(None) == "?" and J._age(None) == "?" and J._num(0) == "0",
              "(8j) отсутствие измерения — «?», а измеренный ноль — «0»: разные вещи"))


# ═══════════ (9) FAIL-SAFE ═══════════
print("\n(9) FAIL-SAFE: не записалось — не потеряно; записалось — второй строки не будет")
try:
    outs, sent, wrote, st = drive(T[:3], {0: [V_SLOW], 1: [V_SLOW]}, {2: ["o5s|1786614515"]},
                                  journal_ok=False)
    res.append(ok(outs[2]["journal"] == [] and "o5s|1786614515" in (st.get("open") or {}),
                  "(9a) мозг не ответил → эпизод НЕ закрыт, скажем на следующем прогоне"))
    # Тяжёлое: строка в мозг легла, а заметка владельцу не ушла → второй строки быть не должно.
    outs, sent, wrote, st = drive(T[:8], {i: [V_FLEET] for i in range(8)},
                                  {7: ["o3|7e348d4"]}, note_ok=False)
    closing = [w for w in wrote if "длилось" in w]
    res.append(ok(len(closing) == 1,
                  "(9b) заметка владельцу упала ПОСЛЕ записи → в журнале всё равно ОДНА "
                  "закрывающая строка: %d" % len(closing)))
    res.append(ok("o3|7e348d4" in (st.get("open") or {}),
                  "(9c) и эпизод остался открытым — владельцу скажем на следующем прогоне"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(9) fail-safe")] * 3


# ═══════════ (10) ОТКАТ ═══════════
print("\n(10) ОТКАТ EXPECT_TO_BRAIN=0 — прежний путь байт-в-байт")
try:
    outs, sent, wrote, st = drive(T[:3], {0: [V_SLOW], 1: [V_SLOW]}, {2: ["o5s|1786614515"]},
                                  brain="0")
    res.append(ok(len(sent) == 2 and "мост отвечает дольше" in sent[0],
                  "(10a) заметка владельцу на ПЕРВОМ такте и закрытие — как до 13.08: %d" % len(sent)))
    res.append(ok(wrote == [], "(10b) в мозг не ушло НИЧЕГО: %s" % wrote))
    res.append(ok(outs[2]["closed"] == ["o5s|1786614515"],
                  "(10c) и эпизод числится closed, как раньше"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(10) откат")] * 3


# ═══════════ (11) ПОРОГ О5 ═══════════
print("\n(11) ПОРОГ О5 240 с: живые 156 и 174 тревоги не дают, 251 даёт")


def slow_facts(dt, now=NOW):
    return {"now": now, "bridge": {"ok": True, "dt": dt, "last_ok": now - 60,
                                   "last_fast": now - 60}}


cfg = E.config({})
res.append(ok(cfg["bridge_slow"] == 240.0,
              "(11a) порог по умолчанию 240 с (был 120, снятый с ЧТЕНИЯ МОЗГА): %s"
              % cfg["bridge_slow"]))
for dt, want in ((156.0, False), (174.0, False), (229.0, False), (251.0, True), (417.0, True)):
    got = bool(E._o5(slow_facts(dt), cfg, NOW))
    res.append(ok(got is want, "(11b) опрос очереди %.0f с → тревога=%s (ждали %s)"
                                % (dt, got, want)))
old = E.config({"EXPECT_BRIDGE_SLOW_SEC": "120"})
res.append(ok(bool(E._o5(slow_facts(174.0), old, NOW)),
              "(11c) EXPECT_BRIDGE_SLOW_SEC=120 возвращает прежнее поведение — ручка жива"))
res.append(ok(not E._o5(slow_facts(417.0), E.config({"EXPECT_BRIDGE_SLOW_SEC": "0"}), NOW),
              "(11d) EXPECT_BRIDGE_SLOW_SEC=0 — ветка мертва (откат)"))
res.append(ok(E.NOTE_HEAD["o5_bridge_slow"] and "o5_bridge_slow" in E.KINDS,
              "(11e) сам вердикт не тронут: вид на месте, заголовок прежний"))


# ═══════════ (12) ИЗОЛЯЦИЯ ═══════════
print("\n(12) ИЗОЛЯЦИЯ: под тестом в боевой мозг не пишется ничего")
try:
    box = []

    class _Boom:
        def __getattr__(self, _n):
            raise AssertionError("под тестом мост звать НЕЛЬЗЯ")

    import cclog
    keep_w = cclog.write_cclog
    cclog.write_cclog = lambda *a, **k: box.append(a) or True
    try:
        got = ER.write_journal("ОЖИДАНИЕ О5 · фикстура")
    finally:
        cclog.write_cclog = keep_w
    res.append(ok(got is True and box == [],
                  "(12a) признак тест-прогона стоит → канонический писатель НЕ звался: %s" % box))
    res.append(ok(ER._is_test_run() is True, "(12b) и признак прогона распознан"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(12) изоляция")] * 2

# ═══════════ (13) ЗАМОК: НЕПУСТОЙ ЗАМЕР НЕ СТАНОВИТСЯ НУЛЁМ ═══════════
# ЖИВОЙ ПОВОД (единственная запись слоя в мозге на 13.08 13:46): «ОЖИДАНИЕ О5 · мост отвечает
# дольше отведённого времени · опрос очереди 0 с при отведённых 0 с · длилось 20 мин». Числа БЫЛИ
# измерены — доказательство того же эпизода говорит «занял 127 с при отведённых 120 с», — и
# пропали на переносе эпизода в запись: открыт он был одной редакцией рук, закрыт другой.
print("\n(13) ЗАМОК: замер был непустым → в записи стоит он, а не ноль и не пустота")
ZERO = "0 с при отведённых 0 с"
try:
    # (а) ЖИВАЯ ФОРМА: эпизод продержался два такта и закрылся сам — числа обязаны доехать.
    outs, sent, wrote, st = drive(T[:3], {0: [V_SLOW], 1: [V_SLOW]}, {2: ["o5s|1786614515"]})
    closing = [w for w in wrote if "длилось" in w]
    res.append(ok(len(closing) == 1 and "174" in closing[0] and "120" in closing[0],
                  "(13a) замер и порог доехали в запись: %s"
                  % (closing[0][:120] if closing else wrote)))
    res.append(ok(all(ZERO not in w and J.NO_NUMBER not in w for w in wrote),
                  "(13b) ни нуля, ни «неизвестно» там, где замер БЫЛ: %s" % wrote))
    # (б) ГЛАВНЫЙ ЗАМОК. Поля вердикта доезжают в запись через белый список ИМЁН (`_KEEP_V`), и
    #     ровно он подвёл живьём: запись прежней редакции его не проходила. Снимаем dt/limit из
    #     списка — это и есть та ситуация (а заодно завтрашний вид, чьё поле в список не внесли).
    #     Число обязано уцелеть: руки снимают его ГОТОВОЙ строкой в момент обнаружения.
    keep_v = ER._KEEP_V
    ER._KEEP_V = tuple(k for k in keep_v if k not in ("dt", "limit"))
    try:
        _o2, _s2, wrote2, _st2 = drive(T[:3], {0: [V_SLOW], 1: [V_SLOW]},
                                       {2: ["o5s|1786614515"]})
    finally:
        ER._KEEP_V = keep_v
    closing2 = [w for w in wrote2 if "длилось" in w]
    res.append(ok(len(closing2) == 1 and "174" in closing2[0] and "120" in closing2[0]
                  and ZERO not in closing2[0],
                  "(13c) поля вердикта до записи НЕ доехали, а замер доехал: %s"
                  % (closing2[0][:120] if closing2 else wrote2)))
    # (в) ДОСЛОВНЫЙ ЖИВОЙ ЭПИЗОД o5s|1786626993: заведён прежней редакцией, замера в его записи
    #     нет вовсе → «неизвестно», а НЕ ноль. Это принятый контракт, а не поражение.
    legacy_st = {"open": {"o5s|1786626993": {"first": NOW - 1200, "kind": "o5_bridge_slow"}}}
    _o3, _s3, wrote3, _st3 = drive([NOW], {}, {0: ["o5s|1786626993"]}, st0=legacy_st)
    res.append(ok(len(wrote3) == 1 and J.NO_NUMBER in wrote3[0] and ZERO not in wrote3[0],
                  "(13d) запись прежней редакции: «неизвестно», а не нули: %s"
                  % (wrote3[0][:140] if wrote3 else wrote3)))
    # (г) ИЗМЕРЕННЫЙ НОЛЬ — ЭТО ФАКТ, и руки его не глотают (зеркало 8j на стороне рук).
    res.append(ok("опрос очереди 0 с при отведённых 240 с"
                  == ER.keep_number({}, dict(V_SLOW, dt=0.0, limit=240.0)),
                  "(13e) измеренный ноль сохраняется как ноль: %s"
                  % ER.keep_number({}, dict(V_SLOW, dt=0.0, limit=240.0))))
    res.append(ok(ER.keep_number({}, {"kind": "o5_bridge_slow", "key": "x"}) == "",
                  "(13f) замера нет → руки не выдумывают числа, строка скажет «неизвестно»"))
    # (д) ЧИСЛО ПРИНАДЛЕЖИТ НАЧАЛУ ЭПИЗОДА: строка говорит «начало», и доказательство снято там же.
    _o4, _s4, wrote4, _st4 = drive(T[:3], {0: [V_SLOW], 1: [dict(V_SLOW, dt=999.0)]},
                                   {2: ["o5s|1786614515"]})
    c4 = [w for w in wrote4 if "длилось" in w]
    res.append(ok(len(c4) == 1 and "174" in c4[0] and "999" not in c4[0],
                  "(13g) замер не переписывается поздним тактом: %s"
                  % (c4[0][:120] if c4 else wrote4)))
    # (е) СТРОКА «ДЕРЖИТСЯ» — тот же замок: у самого долгого нарушения число тоже обязано быть.
    _o5, _s5, wrote5, _st5 = drive(T[:8], {i: [V_FLEET] for i in range(8)}, {})
    held = [w for w in wrote5 if "ещё идёт" in w]
    res.append(ok(len(held) == 1 and "7e348d4" in held[0] and J.NO_NUMBER not in held[0]
                  and "при пороге 4 ч 0 мин" in held[0],
                  "(13h) и «держится» несёт замер: %s" % (held[0][:130] if held else wrote5)))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(13) замок нуля")] * 8


print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
