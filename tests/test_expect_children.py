#!/usr/bin/env python3
"""О7 — ДЕТИ КЛИЕНТСКОГО КОНТУРА ПОЛОСЫ ПК (18.08.2026). Регресс.

ПОВОД ДОСЛОВНЫЙ: 18.08 `moderation_bot` пролежал 12 ч 10 м (рекорд окна — 33 ч 52 м, 06.08),
и сервер не сказал НИЧЕГО. О6 судит ВЗЯТУЮ задачу (в момент смерти взятой не было), О4 от
записи о смерти ребёнка наоборот успокаивается — и О4 при этом ВЕРЕН, его предмет иной.

ФИКСТУРЫ СНЯТЫ С ПРОДА, А НЕ ВЫДУМАНЫ. Дословный снимок `read_doc name=cowork_log` 18.08.2026
13:34 UTC (439 190 знаков, 1258 строк, окно 28.07 15:09 → 18.08 13:34). Публикацию строки о
детях завёл коммит соседней полосы `b2bf40d` 18.08 12:35; за 72 минуты вышло ПЯТЬ строк
(12:22, 12:23, 12:42, 12:47, 13:27) — производитель троттлит по своему процессу, а процесс
законно перезапускается. Отрицательная форма («ребёнок не жив») в корпусе НЕ ВСТРЕЧАЛАСЬ ни
разу, и это сказано прямо: её голдены построены в ГРАММАТИКЕ ТОЙ ЖЕ СТРОКИ и на слове, которым
сам производитель называет отказ в ней же («„неизвестно“ … а не „мёртв“»), плюс форма
незнакомая — ею проверяется НАПРАВЛЕНИЕ СОМНЕНИЯ.

ОБА ОТРИЦАТЕЛЬНЫХ ТЕСТА КОНТРАКТА — секции (4) и (5), и оба обязательны.

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение О7 живёт в том же доказанно безруком модуле
(2)  ЖИВАЯ ФОРМА: дословная строка 18.08 разбирается по детям, период читается
(3)  ПОЗИЦИЯ: цитата формы в прозе отчёта строкой производителя НЕ является
(4)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): строка есть, все дети живы → тревоги НЕТ
(5)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): ребёнок назван не живым → тревога ЕСТЬ, и в ней ИМЯ
(6)  ТРИ ИСХОДА: «неизвестно» не сливается ни со вторым, ни с первым
(7)  НАПРАВЛЕНИЕ СОМНЕНИЯ: незнакомое слово — отказ; отрицание над «работает» — отказ
(8)  ПОРОГ ОТ ПЕРИОДА: 720 мин = два объявленных периода; строка старше — содержания не даёт
(9)  НЕ ВТОРОЙ О4: просрочка судится ТОЛЬКО при живой полосе, иначе молчим
(10) ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО: на каждую дырку в фактах — «проверить не удалось»
(11) ЗАКРЫТИЕ: только ДОКАЗАННЫМ фактом; молчание источника выздоровлением не считается
(12) ОТКАТ: EXPECT_PC_CHILD_MIN=0 → ветка мертва ДО фактов, лишнего вызова моста нет
(13) ФОРМА ЗАМЕТКИ: без кнопок, без номера, без «да»; «дети мертвы» не говорится НИКОГДА
(14) ГРОМКОСТЬ ОТДЕЛЕНА ОТ ВЕРДИКТА: адрес, вес и число журнальной строки
(15) РУКИ: журнал читается ОДИН раз и кормит ТРИ ожидания; своего вызова у О7 нет
(16) ЖИВОЙ СНИМОК 18.08: вердиктов О7 ноль, и это третий исход, а не «дети живы»
(17) СОСЕДИ НЕ ЗАДЕТЫ: О4, О5 и О6 на тех же фактах отвечают как отвечали
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import expectations as E  # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
MIN = 60.0
HOUR = 3600.0
NOW = E.parse_iso("2026-08-18T13:34:00Z")          # момент живого снимка

# ── ДОСЛОВНЫЕ ЖИВЫЕ СТРОКИ (снимок 18.08.2026 13:34 UTC) ───────────────────────────────────
TAIL = ("· ПЕРИОДИЧЕСКАЯ строка (период 360 мин), а не тревога: «неизвестно» здесь значит "
        "«проверить не удалось», а не «мёртв»; её молчание значит «полоса не даёт оборота либо "
        "ПК не наблюдает», а не «с детьми всё хорошо»  ")
NO_TOOL = "неизвестно (прибора о его продукте на этой полосе нет)"
PULSE_1327 = (
    "NOTE 2026-08-18 13:27 UTC: ПУЛЬС · ПК · контур жив: оборот poll_once 1 мин назад · дети "
    "контура: pc_agent — %s ; userbot — %s ; moderation_bot — неизвестно (запись в IPC есть и "
    "она не стара, но процесса с номером из лока в системе нет — писал не модербот) %s"
    % (NO_TOOL, NO_TOOL, TAIL))
PULSE_1247 = (
    "NOTE 2026-08-18 12:47 UTC: ПУЛЬС · ПК · контур жив: оборот poll_once 1 мин назад · дети "
    "контура: pc_agent — %s ; userbot — %s ; moderation_bot — делает работу (свой продукт 0 с "
    "назад) %s" % (NO_TOOL, NO_TOOL, TAIL))
# Живое окружение той же минуты: полоса ПИШЕТ (это и есть признак О4 «след жизни»).
LANE_LIVE = (
    "NOTE 2026-08-18 13:34 UTC: Orchestrator: вотчдог поднял moderation_bot (смерть 1/3, "
    "лежал 5 ч 54 м, PID 10948): moderation_bot запущен (PID 10948).  \n"
    "NOTE 2026-08-18 13:33 UTC: Orchestrator: watchdog: поднял демон через schtasks "
    "(лежал 6 м 52 с, подъём №2 за сутки, PID 15988)  \n"
    "NOTE 2026-08-18 13:13 UTC: Orchestrator: задача #64 → done · Инструкция автологона "
    "поднята в узел карты  \n"
    "NOTE 2026-08-18 13:04 UTC: Orchestrator: взял задачу #64 (in_progress)  \n"
)
# ДОСЛОВНЫЙ отчёт задачи #62 — той самой, что публикацию и завела. Проза о форме, не форма.
REPORT_62 = (
    "NOTE 2026-08-18 12:35 UTC: Orchestrator: задача #62 → done · Вердикт О3 о детях контура "
    "теперь публикуется наружу периодической строкой журнала (6 ч) формой уже существующего "
    "пульса демона; прибор, порог и ветки не тронуты. Коммиты `b2bf40d` (код+тесты) и "
    "`bd65d99` (артефакт).  \n")


def line_with(children, stamp="2026-08-18 13:27"):
    """Строка производителя ТОЙ ЖЕ грамматики с заданными состояниями детей."""
    body = " ; ".join("%s — %s" % (n, s) for n, s in children)
    return ("NOTE %s UTC: ПУЛЬС · ПК · контур жив: оборот poll_once 1 мин назад · дети "
            "контура: %s %s\n" % (stamp, body, TAIL))


ALL_ALIVE = line_with([("pc_agent", "делает работу (свой продукт 3 с назад)"),
                       ("userbot", "делает работу (свой продукт 1 с назад)"),
                       ("moderation_bot", "делает работу (свой продукт 0 с назад)")])
DEAD_MOD = line_with([("pc_agent", "делает работу (свой продукт 3 с назад)"),
                      ("userbot", "делает работу (свой продукт 1 с назад)"),
                      ("moderation_bot", "мёртв (продукта нет 5 ч 54 м при пороге 15 мин)")])


def cfg(**kw):
    c = E.config({})
    c.update(kw)
    return c


C = cfg()


def facts(text, now, fetched=None, bridge_dt=2.1, ok_read=True, bridge_ok=True, **kw):
    """Снимок фактов ровно той формы, что собирают руки (`expectations_run.snapshot`)."""
    cw = E.cowork_facts(text, now) if text is not None else {}
    pc = {"ok": ok_read, "fetched": (now if fetched is None else fetched),
          "last": cw.get("last"), "line": cw.get("line"), "n": cw.get("n"),
          "lane": E.pc_lane_facts(text, now) if text is not None else None,
          "children": E.pc_children_facts(text, now) if text is not None else None}
    pc.update(kw.pop("pc", {}))
    f = {"now": now, "pc": pc,
         "bridge": {"ok": bridge_ok, "dt": bridge_dt,
                    "last_ok": now if bridge_ok else now - 10 * HOUR, "last_fast": now}}
    f.update(kw)
    return f


def o7(text, now, **kw):
    """Только вердикты О7 — соседей отбрасываем, чтобы судить свой предмет."""
    c = kw.pop("cfg", None) or C
    return [v for v in E.verdict(facts(text, now, **kw), c)
            if str(v.get("kind") or "").startswith("o7")]


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══
print("\n(1) граница устройством: решение О7 живёт в безруком модуле")
import ast  # noqa: E402

src = open(os.path.join(REPO, "expectations.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom):
        imports.add((node.module or "").split(".")[0])
res.append(ok(imports == {"re", "datetime"},
              "(1) импортов по-прежнему ровно два (%s) — ни ФС, ни сети, ни моста"
              % sorted(imports)))
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
res.append(ok(not ({"open", "exec", "eval", "subprocess"} & names),
              "(1) ни open, ни exec, ни subprocess в модуле решения нет"))
res.append(ok(all(not v.get("can_task") for v in o7(DEAD_MOD + LANE_LIVE, NOW)),
              "(1) задачи у О7 не бывает НИКОГДА: лечение живёт на чужой машине"))
res.append(ok(E.task_text({"kind": "o7_child_down", "can_task": True, "age": 60}) == "",
              "(1) даже с подделанным can_task текста задачи у О7 нет"))

# ═══ (2) ЖИВАЯ ФОРМА ═══
print("\n(2) живая форма: дословная строка 18.08 разбирается по детям")
ch = E.pc_children_facts(PULSE_1327 + "\n" + PULSE_1247 + "\n" + LANE_LIVE, NOW)
res.append(ok(ch["n"] == 2 and E.utc_stamp(ch["ts"]).startswith("2026-08-18 13:27"),
              "(2) берётся ПОСЛЕДНЯЯ строка о детях (13:27 из двух)"))
res.append(ok(ch["period"] == 360.0, "(2) объявленный период прочитан: %s" % ch["period"]))
got = [(c["name"], c["state"]) for c in ch["children"]]
res.append(ok(got == [("pc_agent", E.CH_UNKNOWN), ("userbot", E.CH_UNKNOWN),
                      ("moderation_bot", E.CH_UNKNOWN)],
              "(2) трое детей разобраны поимённо: %s" % got))
res.append(ok("писал не модербот" in ch["children"][2]["said"],
              "(2) длинное тире ВНУТРИ пояснения имени не рвёт: слово источника целое"))
ch47 = E.pc_children_facts(PULSE_1247, NOW)
res.append(ok([c["state"] for c in ch47["children"]][2] == E.CH_ALIVE,
              "(2) «делает работу (свой продукт 0 с назад)» = ЖИВ"))
res.append(ok(E.pc_children_facts(LANE_LIVE, NOW)["ts"] is None,
              "(2) в журнале без пульса о детях строки нет — и это отсутствие факта"))

# ═══ (3) ПОЗИЦИЯ ═══
print("\n(3) позиция: цитата формы в прозе отчёта строкой производителя не является")
res.append(ok(E.pc_children_facts(REPORT_62, NOW)["n"] == 0,
              "(3) дословный отчёт задачи #62 о САМОЙ публикации пульсом не считается"))
quote = ("NOTE 2026-08-18 13:40 UTC: Orchestrator: задача #70 → done · привожу форму дословно: "
         "«ПУЛЬС · ПК · контур жив: дети контура: moderation_bot — мёртв (продукта нет)» — "
         "разбор закончен  \n")
res.append(ok(E.pc_children_facts(quote, NOW)["n"] == 0 and not o7(quote + LANE_LIVE, NOW),
              "(3) ЦИТАТА мёртвого ребёнка внутри отчёта тревоги НЕ рождает"))
res.append(ok(E.pc_children_facts(PULSE_1327, NOW)["n"] == 1,
              "(3) а та же форма в ЗАЯВЛЯЮЩЕЙ позиции — считается"))

# ═══ (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а) ═══
print("\n(4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): строка есть и все дети живы → тревоги НЕТ")
f_alive = facts(ALL_ALIVE + LANE_LIVE, NOW)
st_alive, info_alive = E.children_state(f_alive, C, NOW)
res.append(ok(st_alive == E.CH_ALIVE, "(4) состояние: «%s»" % st_alive))
res.append(ok(o7(ALL_ALIVE + LANE_LIVE, NOW) == [], "(4) вердиктов О7 ноль"))
res.append(ok(sorted(info_alive["states"].values()) == [E.CH_ALIVE] * 3,
              "(4) живыми названы все трое, и это ДОКАЗАНО строкой, а не молчанием"))
for hrs in (0.1, 1, 3, 6, 11):
    res.append(ok(o7(ALL_ALIVE + LANE_LIVE, NOW + hrs * HOUR,
                     fetched=NOW + hrs * HOUR) == [],
                  "(4) той же строке %s ч — тревоги по-прежнему нет" % hrs))

# ═══ (5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б) ═══
print("\n(5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): ребёнок назван не живым → тревога ЕСТЬ, и в ней ИМЯ")
dead = o7(DEAD_MOD + LANE_LIVE, NOW)
res.append(ok(len(dead) == 1 and dead[0]["kind"] == "o7_child_down",
              "(5) ровно один вердикт, вид «o7_child_down»"))
res.append(ok(dead and dead[0].get("child") == "moderation_bot",
              "(5) ИМЯ ребёнка названо полем вердикта: %s"
              % (dead[0].get("child") if dead else None)))
note5 = E.render(dead[0], "VPS") if dead else ""
res.append(ok("moderation_bot" in note5, "(5) имя стоит и в самой заметке"))
res.append(ok("мёртв (продукта нет 5 ч 54 м при пороге 15 мин)" in note5,
              "(5) слово источника цитируется ДОСЛОВНО, а не пересказывается"))
res.append(ok(dead and dead[0]["key"] == "o7|moderation_bot",
              "(5) ключ эпизода — ИМЯ: пока ребёнок лежит, нарушение одно"))
# Форма отказа не одна: проверяем ЧЕТЫРЕ разных, включая незнакомую.
for said, why in (("не даёт продукта (тик молчит 21 мин при пороге 15)", "отрицание глагола"),
                  ("не жив (лока нет, процесса нет)", "прямое «не жив»"),
                  ("умер (три смерти подряд, вотчдог остановлен)", "незнакомый глагол"),
                  ("залип (event-loop стоит 40 мин, PID жив)", "незнакомое слово")):
    t = line_with([("pc_agent", "делает работу (0 с)"), ("userbot", "делает работу (0 с)"),
                   ("moderation_bot", said)])
    v = o7(t + LANE_LIVE, NOW)
    res.append(ok(len(v) == 1 and v[0].get("child") == "moderation_bot",
                  "(5) %s → тревога с именем: «%s»" % (why, said[:38])))
# ДВОЕ мёртвых — ДВА эпизода: у каждого ребёнка свой ключ и своё выздоровление.
two = o7(line_with([("pc_agent", "делает работу (0 с)"),
                    ("userbot", "не даёт продукта (молчит 2 ч)"),
                    ("moderation_bot", "мёртв (продукта нет)")]) + LANE_LIVE, NOW)
res.append(ok(sorted(v["key"] for v in two) == ["o7|moderation_bot", "o7|userbot"],
              "(5) двое не живы → два эпизода, по одному на ребёнка"))

# ═══ (6) ТРИ ИСХОДА ═══
print("\n(6) три исхода: «неизвестно» не сливается ни со вторым, ни с первым")
f_unk = facts(PULSE_1327 + LANE_LIVE, NOW)
st_unk, info_unk = E.children_state(f_unk, C, NOW)
res.append(ok(st_unk == E.CH_UNKNOWN and st_unk != E.CH_DOWN and st_unk != E.CH_ALIVE,
              "(6) три слова РАЗНЫЕ: «%s» ≠ «%s» ≠ «%s»" % (E.CH_ALIVE, E.CH_DOWN, E.CH_UNKNOWN)))
res.append(ok(not o7(PULSE_1327 + LANE_LIVE, NOW),
              "(6) «неизвестно» о ребёнке эпизода НЕ рождает (иначе он не закрылся бы никогда)"))
res.append(ok(len(info_unk["unknown"]) == 3 and not info_unk["down"],
              "(6) …и в отказ он при этом НЕ записан: не проверено 3, не живых 0"))
mixed = facts(line_with([("pc_agent", NO_TOOL), ("userbot", NO_TOOL),
                         ("moderation_bot", "делает работу (свой продукт 0 с назад)")])
              + LANE_LIVE, NOW)
st_mix, info_mix = E.children_state(mixed, C, NOW)
res.append(ok(st_mix == E.CH_UNKNOWN and info_mix["alive"] == ["moderation_bot"],
              "(6) один жив, двое не проверены → «дети живы» СКАЗАТЬ НЕЛЬЗЯ"))
res.append(ok(E.CH_UNKNOWN == "проверить не удалось",
              "(6) третий исход называет себя словами, а не молчанием: «%s»" % E.CH_UNKNOWN))

# ═══ (7) НАПРАВЛЕНИЕ СОМНЕНИЯ ═══
print("\n(7) направление сомнения: незнакомое слово — отказ, а не благополучие")
res.append(ok(E.child_state("делает работу (свой продукт 0 с назад)") == E.CH_ALIVE,
              "(7) живая положительная форма — ЖИВ"))
res.append(ok(E.child_state("не работает (продукта нет)") == E.CH_DOWN,
              "(7) «не работает» НЕ читается как «работает» (отрицание сильнее стема)"))
res.append(ok(E.child_state("жив (продукт 2 с назад)") == E.CH_ALIVE,
              "(7) «жив» — положительная форма"))
res.append(ok(E.child_state("не жив (продукта нет)") == E.CH_DOWN, "(7) «не жив» — отказ"))
res.append(ok(E.child_state("неизвестно (прибора о его продукте на этой полосе нет)")
              == E.CH_UNKNOWN,
              "(7) «неизвестно» — третий исход, хотя внутри пояснения стоит «нет»"))
res.append(ok(E.child_state("проверить не удалось (лок нечитаем)") == E.CH_UNKNOWN,
              "(7) родня третьего исхода читается им же, а не отказом из-за «не»"))
res.append(ok(E.child_state("абракадабра (что-то новое)") == E.CH_DOWN,
              "(7) НЕЗНАКОМОЕ слово — ОТКАЗ: цена ошибки сюда одна строка, обратно — мёртвый бот"))
res.append(ok(E.child_state("") == E.CH_UNKNOWN and E.child_state(None) == E.CH_UNKNOWN,
              "(7) пусто — это НАШ непрочит, а не заявление источника: «проверить не удалось»"))
res.append(ok(E.child_state("делает работу (умер бы, но не умер)") == E.CH_ALIVE,
              "(7) слова о смерти ВНУТРИ пояснения решения не меняют: судится голова фразы"))

# ═══ (8) ПОРОГ ОТ ПЕРИОДА ═══
print("\n(8) порог 720 мин = два объявленных периода публикации (360)")
res.append(ok(C["pc_child"] == 720 * MIN, "(8) дефолт 720 мин: %s с" % C["pc_child"]))
res.append(ok(C["pc_child"] == 2 * E.CHILD_PERIOD_DECLARED * MIN,
              "(8) и это РОВНО два объявленных периода, а не круглое число с потолка"))
PULSE_TS = E.parse_iso("2026-08-18T13:27:00Z")        # штамп самой строки, а не момент снимка
old = PULSE_TS + 11 * HOUR + 59 * MIN                 # строке 11 ч 59 м — ещё судим содержание
res.append(ok(o7(DEAD_MOD + LANE_LIVE, old, fetched=old)[0]["kind"] == "o7_child_down",
              "(8) 11 ч 59 м: содержание строки ещё судится"))
lost_now = PULSE_TS + 12 * HOUR + 1 * MIN
# Полоса ЖИВА (пишет), а публикации о детях нет 12 ч 01 м → просрочка.
LANE_FRESH = ("NOTE 2026-08-19 01:35 UTC: Orchestrator: взял задачу #71 (in_progress)  \n")
lost = o7(DEAD_MOD + LANE_FRESH, lost_now, fetched=lost_now)
res.append(ok(len(lost) == 1 and lost[0]["kind"] == "o7_pulse_lost",
              "(8) 12 ч 01 м: содержание больше НЕ судится, исход — просрочка"))
note8 = E.render(lost[0], "VPS") if lost else ""
res.append(ok("назван не живым" not in note8 and "это НЕ «дети мертвы»" in note8,
              "(8) и просрочка смерти НЕ утверждает — она прямо от неё открещивается"))
res.append(ok(lost and lost[0]["key"] == "o7l|%d" % int(E.parse_iso("2026-08-18T13:27:00Z")),
              "(8) ключ просрочки — последняя известная публикация"))

# ═══ (9) НЕ ВТОРОЙ О4 ═══
print("\n(9) не второй О4: просрочка судится ТОЛЬКО при живой полосе")
silent_now = E.parse_iso("2026-08-19T13:00:00Z")       # 23 ч 33 м после последней строки
sil = facts(DEAD_MOD + LANE_LIVE, silent_now, fetched=silent_now)
kinds9 = {v["kind"] for v in E.verdict(sil, C)}
res.append(ok("o4_pc_silent" in kinds9, "(9) полоса молчит 23 ч → говорит О4, как и раньше"))
res.append(ok(not [k for k in kinds9 if k.startswith("o7")],
              "(9) …а О7 при этом МОЛЧИТ: об одном факте дважды не кричим"))
res.append(ok(len(lost) == 1 and E.pc_state(facts(DEAD_MOD + LANE_FRESH, lost_now,
                                                  fetched=lost_now), C, lost_now)[0]
              == E.PC_ALIVE,
              "(9) обратный случай (полоса пишет, публикация пропала) — вот он и интересен"))

# ═══ (10) ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО ═══
print("\n(10) замок: на каждую дырку в фактах — «проверить не удалось», а не «жив»")
# Канал стоит ОТДЕЛЬНО и намеренно: содержание строки он не портит (снимок у нас свежий), но
# говорить о соседней полосе при недоказанном канале нельзя — тот же рубеж, что у О4 и О6.
f_nobridge = facts(DEAD_MOD + LANE_LIVE, NOW, bridge_ok=False)
res.append(ok(not [v for v in E.verdict(f_nobridge, C) if str(v["kind"]).startswith("o7")],
              "(10) канал не доказан живым → об О7 не говорится НИЧЕГО (рубеж О4/О6)"))
holes = [
    ("журнал не прочитан", facts(DEAD_MOD + LANE_LIVE, NOW, ok_read=False)),
    ("срез устарел", facts(DEAD_MOD + LANE_LIVE, NOW, fetched=NOW - 40 * MIN)),
    ("фактов о ПК нет вовсе", {"now": NOW, "pc": None,
                               "bridge": {"ok": True, "dt": 2.0, "last_ok": NOW}}),
    ("запись прежней редакции (без разбора детей)",
     facts(DEAD_MOD + LANE_LIVE, NOW, pc={"children": None})),
]
for why, f in holes:
    st10 = E.children_state(f, C, NOW)[0]
    v10 = [v for v in E.verdict(f, C) if str(v["kind"]).startswith("o7")]
    res.append(ok(st10 == E.CH_UNKNOWN and st10 != E.CH_ALIVE and not v10,
                  "(10) %s → «%s», и ни одного вердикта О7" % (why, st10)))
res.append(ok(E.children_state(facts(ALL_ALIVE + LANE_LIVE, NOW, ok_read=False), C, NOW)[0]
              != E.CH_ALIVE,
              "(10) даже когда ПРОШЛАЯ строка говорила «все живы» — непрочитанный журнал не «жив»"))

# ═══ (11) ЗАКРЫТИЕ ═══
print("\n(11) закрытие: только ДОКАЗАННЫМ фактом")
key = "o7|moderation_bot"
res.append(ok(key in E.closures(facts(ALL_ALIVE + LANE_LIVE, NOW), C, [key]),
              "(11) свежая строка называет ЭТОГО ребёнка живым → эпизод закрыт"))
res.append(ok(key not in E.closures(facts(PULSE_1327 + LANE_LIVE, NOW), C, [key]),
              "(11) «неизвестно» о нём НЕ закрывает: молчание источника не выздоровление"))
res.append(ok(key not in E.closures(facts(DEAD_MOD + LANE_LIVE, NOW), C, [key]),
              "(11) пока он назван не живым — закрывать нечего"))
res.append(ok(key not in E.closures(facts(ALL_ALIVE + LANE_LIVE, NOW, ok_read=False), C, [key]),
              "(11) журнал не прочитан → эпизод жив, скажем позже"))
gone = line_with([("pc_agent", "делает работу (0 с)"), ("userbot", "делает работу (0 с)")])
res.append(ok(key not in E.closures(facts(gone + LANE_LIVE, NOW), C, [key]),
              "(11) ребёнок ПРОПАЛ из строки → это не выздоровление, эпизод держим"))
other = "o7|userbot"
mixed_close = E.closures(facts(line_with([("pc_agent", "делает работу (0 с)"),
                                          ("userbot", "делает работу (0 с)"),
                                          ("moderation_bot", "мёртв (продукта нет)")])
                               + LANE_LIVE, NOW), C, [key, other])
res.append(ok(other in mixed_close and key not in mixed_close,
              "(11) выздоровел один — закрылся ОДИН эпизод, у второго свой ключ"))
klost = "o7l|%d" % int(E.parse_iso("2026-08-18T13:27:00Z"))
res.append(ok(klost in E.closures(facts(PULSE_1327 + LANE_LIVE, NOW), C, [klost]),
              "(11) публикация вернулась в срок → просрочка закрыта, даже если дети «неизвестно»"))
res.append(ok(klost not in E.closures(facts(DEAD_MOD + LANE_FRESH, lost_now,
                                            fetched=lost_now), C, [klost]),
              "(11) пока публикации нет — просрочка держится"))

# ═══ (12) ОТКАТ ═══
print("\n(12) откат: EXPECT_PC_CHILD_MIN=0 → ветка мертва ДО чтения фактов")
c0 = cfg(pc_child=0.0)
res.append(ok(E.children_state(facts(DEAD_MOD + LANE_LIVE, NOW), c0, NOW)[0] == E.CH_UNKNOWN,
              "(12) состояние — «неизвестно», а не «жив» (откат не врёт)"))
res.append(ok(not [v for v in E.verdict(facts(DEAD_MOD + LANE_LIVE, NOW), c0)
                   if str(v["kind"]).startswith("o7")],
              "(12) ни одного вердикта О7 при выключенном пороге"))
res.append(ok(E.limit_env(E.PC_CHILD_ENV, E.PC_CHILD_DEFAULT, {"EXPECT_PC_CHILD_MIN": "0"}) == 0,
              "(12) ноль в окружении ЗНАЧИМ — своим парсером, а не `_env_int` демона"))
res.append(ok(E.limit_env(E.PC_CHILD_ENV, E.PC_CHILD_DEFAULT, {}) == 720 * MIN,
              "(12) пусто → дефолт 720 мин"))
kinds12 = {v["kind"] for v in E.verdict(facts(DEAD_MOD + LANE_LIVE, NOW), c0)}
res.append(ok(kinds12 == {v["kind"] for v in E.verdict(facts(DEAD_MOD + LANE_LIVE, NOW),
                                                       cfg(pc_child=0.0))},
              "(12) прочие ожидания при откате отвечают ровно как отвечали"))

# ═══ (13) ФОРМА ЗАМЕТКИ ═══
print("\n(13) форма заметки: без кнопок, без номера, без «да»")
note_down = E.render(dead[0], "VPS")
note_lost = E.render(lost[0], "VPS")
import re as _re  # noqa: E402

for name, txt in (("отказ", note_down), ("просрочка", note_lost)):
    # СЛОВО, а не подстрока: «периода» кончается на «да», и наивный поиск нашёл бы ответ там,
    # где его нет (тот же класс, против которого заведено правило позиции).
    res.append(ok(not _re.search(r"(?<![а-яё])да(?![а-яё])", txt.lower())
                  and "approve" not in txt.lower()
                  and "кнопк" not in txt.lower() and "NEEDS_APPROVAL" not in txt,
                  "(13) %s: ни кнопки, ни номера, ни слова «да»" % name))
    res.append(ok(txt.startswith("🔔") and txt.endswith(E.TAIL),
                  "(13) %s: то же семейство и та же граница владельца в хвосте" % name))
res.append(ok("сказать о них нечего" in note_lost and "не знаю" in note_lost,
              "(13) просрочка называет себя третьим исходом СВОИМИ словами"))
res.append(ok("2026-08-18 13:27" in note_down,
              "(13) отказ называет АБСОЛЮТНОЕ время строки, по которой судит"))
res.append(ok("pc_agent" in note_down and "userbot" in note_down,
              "(13) …и что сказано о прочих детях той же строки"))
res.append(ok("не гадаю" in note_down,
              "(13) о ПРИЧИНЕ смерти ребёнка прибор не гадает — он передаёт слово источника"))

# ═══ (14) ГРОМКОСТЬ ОТДЕЛЕНА ОТ ВЕРДИКТА ═══
print("\n(14) громкость отделена от вердикта: адрес, вес, число")
import expect_journal as J  # noqa: E402

f14 = facts(DEAD_MOD + LANE_LIVE, NOW)
loud = J.address(dead[0], f14, held=2 * HOUR, defer=HOUR, frozen_client=True)
quiet = J.address(dead[0], f14, held=5 * MIN, defer=HOUR, frozen_client=True)
res.append(ok(loud[0] == J.BRAIN_AND_OWNER and "moderation_bot" in loud[1],
              "(14) переживший отсрочку отказ — владельцу, и причина называет ребёнка"))
res.append(ok(quiet[0] == J.BRAIN and "отсрочку ещё не пережило" in quiet[1],
              "(14) погасший быстрее отсрочки владельцу не показывается…"))
res.append(ok(J.line(dead[0], "VPS", NOW - HOUR, NOW, "закрыт", 6, "",
                     num=J.number(dead[0])).count("О7") == 1,
              "(14) …но в счёт входит: строка эпизода уходит в мозг ВСЕГДА"))
jl = J.line(dead[0], "VPS", NOW - HOUR, NOW, "закрыт", 6, "", num=J.number(dead[0]))
res.append(ok("moderation_bot" in jl and "порог" in jl,
              "(14) число замера называет РЕБЁНКА и порог: %s" % jl[:100]))
res.append(ok(J.address(lost[0], f14, held=10 * HOUR, defer=HOUR, frozen_client=True)[0]
              == J.BRAIN,
              "(14) просрочка — только в мозг: решать по незнанию владельцу нечего"))
before14 = dict(dead[0])
J.address(dead[0], f14, held=0, defer=HOUR, frozen_client=True)
res.append(ok(before14 == dead[0], "(14) выбор адреса не тронул вердикт НИ ОДНИМ полем"))
# СОСЕДИ ПО ВЕСУ НЕ СДВИНУЛИСЬ: ветка О4/О6 осталась ровно такой, какой была.
res.append(ok(J.heavy({"kind": "o4_pc_silent", "line": "x"}, None, True)[0] is False
              and J.heavy({"kind": "o6_pc_task", "line": "x"}, None, True)[0] is False
              and J.heavy({"kind": "o4_pc_silent", "line": "x"}, None, False)[0] is True,
              "(14) вес О4 и О6 не изменён ни в одну сторону"))
res.append(ok(J.number({"kind": "o7_child_down"}) == J.NO_NUMBER,
              "(14) числа нет → так и сказано, а не ноль"))

# ═══ (15) РУКИ ═══
print("\n(15) руки: ОДНО чтение журнала кормит ТРИ ожидания, своего вызова у О7 нет")
try:
    import types  # noqa: E402

    import expectations_run as ER  # noqa: E402

    calls = []

    class _FakeBC:
        def __init__(self, timeout=None):
            pass

        def _call(self, action, **kw):
            calls.append((action, kw))
            return {"ok": True, "text": DEAD_MOD + LANE_LIVE}

    fake = types.ModuleType("bridge_client")
    fake.BridgeClient = _FakeBC
    real = sys.modules.get("bridge_client")
    sys.modules["bridge_client"] = fake
    try:
        st = {}
        p = ER.pc_facts(st, NOW, C)
        res.append(ok(len(calls) == 1 and calls[0][0] == "read_doc"
                      and calls[0][1] == {"name": "cowork_log"},
                      "(15) журнал открыт ПО ИМЕНИ через живой реестр моста, id не хардкодится"))
        res.append(ok(isinstance(p.get("children"), dict) and p["children"]["ts"] is not None
                      and p.get("lane") is not None and p.get("last") is not None,
                      "(15) ОДНО чтение принесло факты О4, О6 и О7 разом"))
        calls[:] = []
        # ЧИТАТЕЛЕЙ ЖУРНАЛА СТАЛО ЧЕТЫРЕ (18.08.2026, О8 «полоса не выполняет заходов»):
        # выключить чтение вправе только их ОБЩЕЕ молчание, поэтому гасится и четвёртый порог.
        # Предмет проверки прежний — «читателей нет → мосту ни одного вызова».
        ER.pc_facts({}, NOW, cfg(pc=0.0, pc_task=0.0, pc_child=0.0, lane_run=0.0))
        res.append(ok(not calls, "(15) все четыре порога 0 → мост не зовётся ВОВСЕ"))
        calls[:] = []
        ER.pc_facts({}, NOW, cfg(pc=0.0, pc_task=0.0))
        res.append(ok(len(calls) == 1,
                      "(15) при выключенных О4 и О6 журнал читает О7 (откат соседа его не глушит)"))
        # Состояние переживает прогон: разбор детей ложится в st и достаётся следующему прогону.
        st2 = {"pc": {k: p.get(k) for k in ("ok", "fetched", "last", "line", "n", "lane",
                                            "children")}}
        calls[:] = []
        p2 = ER.pc_facts(st2, NOW + 5 * MIN, C)
        res.append(ok(not calls and p2.get("cached") and p2["children"]["ts"] == p["children"]["ts"],
                      "(15) кэш несёт разбор детей — лишнего вызова к мосту нет"))
        d15 = ER.close_detail("o7|moderation_bot", facts(ALL_ALIVE + LANE_LIVE, NOW))
        res.append(ok("делает работу" in d15,
                      "(15) закрытие цитирует СЛОВА источника: %s" % d15[:70]))
        res.append(ok(ER.close_detail("o7|нет-такого", facts(ALL_ALIVE + LANE_LIVE, NOW)) == "",
                      "(15) своих слов нет → молчим, чужих не подставляем"))
        res.append(ok("child" in ER._KEEP_V,
                      "(15) имя ребёнка переживает эпизод в состоянии — иначе число потеряется"))
    finally:
        if real is not None:
            sys.modules["bridge_client"] = real
        else:
            sys.modules.pop("bridge_client", None)
except Exception as e:                                               # noqa: BLE001
    res.append(ok(False, "(15) руки: исключение %r" % e))

# ═══ (16) ЖИВОЙ СНИМОК ═══
print("\n(16) живой снимок 18.08: вердиктов О7 ноль — и это третий исход, а не «дети живы»")
LIVE = PULSE_1327 + "\n" + PULSE_1247 + "\n" + LANE_LIVE + REPORT_62
res.append(ok(not o7(LIVE, NOW), "(16) сегодня тревоги нет: источник сказал «неизвестно»"))
res.append(ok(E.children_state(facts(LIVE, NOW), C, NOW)[0] == E.CH_UNKNOWN,
              "(16) и состояние честно называет это «проверить не удалось»"))
res.append(ok("moderation_bot" in E.children_state(facts(LIVE, NOW), C, NOW)[1]["states"],
              "(16) ребёнок в разборе ЕСТЬ — молчим не потому, что его потеряли"))

# ═══ (17) СОСЕДИ НЕ ЗАДЕТЫ ═══
print("\n(17) соседи: О4, О5 и О6 на тех же фактах отвечают как отвечали")
res.append(ok(E.pc_state(facts(LIVE, NOW), C, NOW)[0] == E.PC_ALIVE,
              "(17) О4: полоса пишет → «подаёт признак жизни»"))
res.append(ok(E.pc_task_state(facts(LIVE, NOW), C, NOW)[0] == E.PCT_MOVING,
              "(17) О6: взятая задача закрыта → «движется»"))
res.append(ok(E.bridge_state(facts(LIVE, NOW), C, NOW)[0] == E.BRIDGE_OK,
              "(17) О5: проба прошла → «отвечает»"))
res.append(ok(len(E.KINDS) == 12 and "o7_child_down" in E.KINDS
              and "o7_pulse_lost" in E.KINDS,
              "(17) видов стало 12 (О8 добавлен 18.08), оба вида О7 названы поимённо"))
res.append(ok(all(k in E.NOTE_HEAD for k in E.KINDS),
              "(17) у каждого вида есть свой заголовок заметки"))
res.append(ok(all(k in J.SHORT and k in J.WHAT for k in E.KINDS),
              "(17) и своё имя в журнале мозга — иначе строка не ищется по теме"))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
