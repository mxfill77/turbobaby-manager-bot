"""СКАН ПРОСРОЧЕК ЧИТАЕТ ТРИ СОСТОЯНИЯ КЛЕТКИ (10.08.2026).

ЖИВОЙ ФАКТ, с которого снят регресс. Перепись
`docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md`: скан насчитал 35 просроченных байков
из 38, и 12 из них попали в счёт ТОЛЬКО потому, что клетка ТО была ПУСТА. Причина — одна строка:

    last = _i(b.get(f"{kind}_last_km")) or 0
    if last <= 0:  →  «не делалось», в ТОТ ЖЕ список просрочек

Пустая клетка, прочерк «-», настоящий ноль и отрицательное приезжали от моста ОДНИМ нулём
(`parseNumber`), и различить их скан не мог в принципе. Мост научен различать (контракт
`fleet_cell`, деплой @79 10.08.2026), и здесь закреплено, что скан этим ПОЛЬЗУЕТСЯ.

ЧТО ЗАКРЕПЛЕНО:
  · ПРОСРОЧКА — только по ЗНАЧЕНИЮ, по которому срок вышел;
  · ПУСТО и НЕ-ЧИСЛО — отдельный исход «НЕ ИЗМЕРЕНО», он называется вслух и в просрочки не идёт;
  · РАЗМЕТКИ НЕТ (старый деплой) — третий исход «НЕ УДАЛОСЬ ПРОВЕРИТЬ», и он НЕ выдаётся ни за
    «не измерено», ни за здоровье: честный вид поверх слепого источника хуже прежнего вранья;
  · три числа НЕ сворачиваются одно в другое ни у скана, ни у доски, ни у владельца;
  · НЕВОЗМОЖНЫЕ значения (отрицательное, ноль, «пробег при покупке больше пробега замены»)
    называются вслух и НЕ ИСПРАВЛЯЮТСЯ: в расчёт идёт то же число, что лежит в листе;
  · доска нарядов не говорит «✅ решено» о байке, который просто перестал быть измеренным.

ЖИВОЙ ФОРМАТ (класс row705→1268 и §8 свода среды): разметка клетки в фикстурах — ДОСЛОВНО та,
что отдаёт прод 10.08.2026, снята с моста этим заходом:
    значение  {"state": "value", "num": 18302, "raw": "18302"}
    пусто     {"state": "empty", "raw": ""}
    не-число  {"state": "text",  "raw": "-"}
Живой мост здесь не трогается: сети нет, Telegram нет, Лист1 не читается и не пишется.

Проверки:
 (1) ТРИ СОСТОЯНИЯ → три исхода скана (значение/пусто/не-число);
 (2) ТРИ ЧИСЛА РАЗДЕЛЬНО — ни одно не свёрнуто в другое;
 (3) НЕВОЗМОЖНЫЕ ЗНАЧЕНИЯ: названы, но не исправлены (расчёт по тому же числу);
 (4) РАЗМЕТКИ НЕТ → всё в «не удалось проверить», ноль просрочек и ноль «не измерено»;
 (5) ГОЛДЕН КЛАССА: фантом уходит из просрочек, настоящая просрочка остаётся;
 (6) ДОСКА: «✅ решено» не говорится о неизмеренном, msg_id сохраняется;
 (7) ВЛАДЕЛЕЦ видит три числа и список невозможных значений.
"""
import os, sys, asyncio, tempfile

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import splinter as S
import devbot as DB
import memory as M
import scan_result as SR

loop = asyncio.new_event_loop()
HQ = S.O3_TEST_CHAT_ID


# --- разметка клетки: ДОСЛОВНО живой формат моста @79 (снят 10.08.2026) ----------------------
def C_VAL(n):   return {"state": "value", "num": n, "raw": str(n)}
def C_EMPTY():  return {"state": "empty", "raw": ""}
def C_TEXT(s):  return {"state": "text", "raw": s}


def bike(name, mileage, oil, gear, abs_, air, mileage_cell=None):
    """Строка парка в ЖИВОЙ форме: плоские поля (как было) + `cells` рядом (как отдаёт мост).

    Значение клетки задаётся РАЗМЕТКОЙ, а плоское поле остаётся тем, чем его видит старый
    потребитель (`_odo_current` берёт фоллбэк-пробег именно оттуда) — ровно как в проде."""
    def flat(c):
        return c.get("num", 0) if c["state"] == "value" else 0
    cells = {"mileage": mileage_cell or C_VAL(mileage), "oil_last_km": oil, "gear_last_km": gear,
             "abs_last_km": abs_, "airfilter_last_km": air}
    return {"name": name, "status": "ДОМА", "mileage": mileage,
            "oil_last_km": flat(oil), "gear_last_km": flat(gear),
            "abs_last_km": flat(abs_), "airfilter_last_km": flat(air), "cells": cells}


class BaseBR:
    """Мост-заглушка. `fleet(cells=…)` — ЖИВАЯ сигнатура: скан просит разметку явным параметром."""
    ROWS = []
    SVC = []
    def _call(s, a, **k): return {"ok": False}          # книга знаний недоступна → фоллбэк-интервалы
    def fleet(s, cells=False):
        rows = [dict(r) for r in s.ROWS]
        if not cells:                                   # без просьбы разметки нет — как в проде
            for r in rows:
                r.pop("cells", None)
        return {"data": {"bikes": rows}}
    def service_list(s): return {"items": list(s.SVC)}


# ═══ (1) ТРИ СОСТОЯНИЯ → ТРИ ИСХОДА ══════════════════════════════════════════════════════════
print("(1) три состояния клетки → три исхода скана:")


class BR3(BaseBR):
    ROWS = [
        # ЗНАЧЕНИЕ, срок вышел: масло 4000, замена на 20000, текущий 30000 → просрочено 6000
        bike("NMAX 155CC PHUKET 4255", 3000, C_VAL(20000), C_VAL(29000), C_VAL(25000), C_VAL(25000)),
        # ПУСТО в ABS и фильтре — прежде это давало ДВЕ просрочки «не делалось»
        bike("NMAX 155CC PHUKET 4256", 3000, C_VAL(29000), C_VAL(29000), C_EMPTY(), C_EMPTY()),
        # НЕ-ЧИСЛО (живой прочерк из Лист1) — прежде тоже «не делалось»
        bike("NMAX 155CC PHUKET 4257", 3000, C_VAL(29000), C_VAL(29000), C_TEXT("-"), C_TEXT("-")),
    ]
    SVC = [{"bike": f"NMAX 155CC PHUKET {n}", "current_km": 30000,
            "updated_at": "2026-08-01T00:00:00Z"} for n in (4255, 4256, 4257)]


scan = S._o3_overdue_scan(BR3())
p = scan.payload
res.append(ok(scan.ok and scan.scanned == 3 and scan.parsed == 3, f"скан состоялся: {scan.say()}"))
res.append(ok(isinstance(p, dict) and set(p) >= {"overdue", "unmeasured", "unchecked", "counts"},
              "payload — словарь трёх исходов, а не один список просрочек"))
res.append(ok([o["plate"] for o in p["overdue"]] == ["4255"],
              f"ПРОСРОЧКА только у байка со ЗНАЧЕНИЕМ — {[o['plate'] for o in p['overdue']]}"))
res.append(ok(p["overdue"][0]["items"][0]["over_km"] == 6000 and p["overdue"][0]["items"][0]["last"] == 20000,
              "просрочка считается от ЗНАЧЕНИЯ клетки: 30000 − (20000+4000) = 6000"))
un = {o["plate"]: o for o in p["unmeasured"]}
res.append(ok(set(un) == {"4256", "4257"}, f"ПУСТО и НЕ-ЧИСЛО → «не измерено» — {sorted(un)}"))
res.append(ok([it["state"] for it in un["4256"]["items"]] == [SR.OUTCOME_EMPTY] * 2,
              "пустая клетка названа своим именем (empty), а не нулём"))
res.append(ok([it["state"] for it in un["4257"]["items"]] == [SR.OUTCOME_MISMATCH] * 2,
              "прочерк «-» назван «не число» (mismatch), а не нулём"))
res.append(ok(all("-" in it["why"] for it in un["4257"]["items"]),
              "и содержимое клетки названо ДОСЛОВНО: " + un["4257"]["items"][0]["why"]))
res.append(ok(not any(o["plate"] in ("4256", "4257") for o in p["overdue"]),
              "ни один неизмеренный байк НЕ попал в просрочки (12 фантомов из 35 — этот класс)"))
res.append(ok(p["unchecked"] == [], "разметка есть у всех → «не удалось проверить» пуст"))
res.append(ok(all(it["due_by_mileage"] for it in un["4256"]["items"]),
              "пробег дорос до интервала → пометка ВНУТРИ «не измерено», а не билет в просрочки"))

# ═══ (2) ТРИ ЧИСЛА РАЗДЕЛЬНО ═════════════════════════════════════════════════════════════════
print("(2) три числа раздельно — ни одно не свёрнуто в другое:")
c = p["counts"]
res.append(ok(c["overdue_bikes"] == 1 and c["overdue_items"] == 1, "просрочено: 1 байк, 1 клетка"))
res.append(ok(c["unmeasured_bikes"] == 2 and c["unmeasured_items"] == 4, "не измерено: 4 клетки у 2 байков"))
res.append(ok(c["unchecked_bikes"] == 0 and c["unchecked_items"] == 0, "не удалось проверить: 0"))
res.append(ok(c["overdue_items"] + c["unmeasured_items"] != c["overdue_items"],
              "«не измерено» не прибавлено к просрочкам"))
line = S._o3_counts_line(p)
res.append(ok("просрочено 1" in line and "не измерено 4" in line and "не удалось проверить 0" in line,
              f"строка владельцу несёт ВСЕ ТРИ числа: «{line}»"))
res.append(ok("байков" in line and "клеток" in line, "и единицы названы (байки против клеток) — числа не сравнимы на глаз"))
bk = c["by_kind"]
res.append(ok(bk["oil"]["overdue"] == 1 and bk["abs"]["unmeasured"] == 2 and bk["airfilter"]["unmeasured"] == 2,
              "разложение ПО РЕГИСТРАМ: масло/редуктор/ABS/фильтр считаются раздельно"))
res.append(ok(set(bk) == set(S._MAND_KINDS), "регистров ровно четыре, как и обязательных видов ТО"))

# ═══ (3) НЕВОЗМОЖНЫЕ ЗНАЧЕНИЯ: назвать, НЕ исправить ═════════════════════════════════════════
print("(3) невозможные значения — названы, но не исправлены:")


class BR_IMP(BaseBR):
    ROWS = [
        # отрицательное (живой случай: XMAX 8969, кол.K = −5000)
        bike("XMAX 300CC NEW BLACK PHUKET 8969", 3000, C_VAL(29000), C_VAL(29000),
             C_VAL(-5000), C_VAL(29000)),
        # настоящий ноль (живой случай: XMAX 1813, кол.K) — замена БЫЛА, на нулевом пробеге
        bike("XMAX 300CC NEW BLUE PHUKET 1813", 3000, C_VAL(29000), C_VAL(29000),
             C_VAL(0), C_VAL(29000)),
        # пробег ПРИ ПОКУПКЕ больше пробега замены (живой случай: NMAX 4255, H=29275 > I=24094).
        # Остальные клетки ВЫШЕ H намеренно: проверяем ровно одну невозможность, а не россыпь.
        bike("NMAX 155CC BLACK GOLD PHUKET 4255", 29275, C_VAL(24094), C_VAL(29500),
             C_VAL(29500), C_VAL(29500)),
    ]
    SVC = [{"bike": r["name"], "current_km": 30000, "updated_at": "2026-08-01T00:00:00Z"}
           for r in ROWS]


imp_scan = S._o3_overdue_scan(BR_IMP())
ip = imp_scan.payload
imp = {(x["plate"], x["kind"]): x for x in ip["impossible"]}
res.append(ok(("8969", "abs") in imp and "отрицательное" in imp[("8969", "abs")]["why"],
              "отрицательное значение названо: " + imp[("8969", "abs")]["why"]))
res.append(ok(("1813", "abs") in imp and "нулев" in imp[("1813", "abs")]["why"],
              "нулевое значение названо: " + imp[("1813", "abs")]["why"]))
res.append(ok(("4255", "oil") in imp and "при покупке" in imp[("4255", "oil")]["why"],
              "пробег при покупке > пробега замены назван: " + imp[("4255", "oil")]["why"]))
res.append(ok(imp[("8969", "abs")]["value"] == -5000 and imp[("1813", "abs")]["value"] == 0,
              "значение в списке — ТО ЖЕ, что в листе (−5000 и 0), а не подчищенное"))
neg = [it for o in ip["overdue"] if o["plate"] == "8969" for it in o["items"] if it["kind"] == "abs"]
res.append(ok(neg and neg[0]["last"] == -5000 and neg[0]["next"] == 5000,
              "в РАСЧЁТ ушло то же −5000 (next = −5000+10000): транспорт не чинит, скан не подменяет"))
zer = [it for o in ip["overdue"] if o["plate"] == "1813" for it in o["items"] if it["kind"] == "abs"]
res.append(ok(zer and zer[0]["last"] == 0 and zer[0]["next"] == 10000,
              "настоящий НОЛЬ остаётся ЗНАЧЕНИЕМ и даёт просрочку (замена была, на нулевом пробеге)"))
res.append(ok(not any(o["plate"] == "1813" for o in ip["unmeasured"]),
              "и НЕ уходит в «не измерено»: ноль-значение ≠ пустая клетка — ради этого весь контракт"))
res.append(ok(all(it.get("impossible") for it in neg + zer),
              "просроченная клетка с невозможным значением несёт пометку прямо в items"))
res.append(ok(len(ip["impossible"]) == 3, f"названы ровно три невозможных значения — {len(ip['impossible'])}"))

# ═══ (4) РАЗМЕТКИ НЕТ → «не удалось проверить», а не «не измерено» ════════════════════════════
print("(4) старый мост (разметки нет) → третий исход, а не выдуманное «пусто»:")


class BR_OLD(BaseBR):
    ROWS = BR3.ROWS
    SVC = BR3.SVC
    def fleet(s, cells=False):                      # старый деплой параметр ИГНОРИРУЕТ
        rows = [dict(r) for r in s.ROWS]
        for r in rows:
            r.pop("cells", None)
        return {"data": {"bikes": rows}}


old = S._o3_overdue_scan(BR_OLD())
op = old.payload
res.append(ok(old.ok and op["overdue"] == [], "без разметки НИ ОДНОЙ просрочки не объявлено"))
res.append(ok(op["unmeasured"] == [], "и ни одного «не измерено» — мы не знаем, что в клетке"))
res.append(ok(op["counts"]["unchecked_items"] == 12 and op["counts"]["unchecked_bikes"] == 3,
              f"всё ушло в «не удалось проверить»: {op['counts']['unchecked_items']} клеток у "
              f"{op['counts']['unchecked_bikes']} байков (три скутера × четыре регистра)"))
res.append(ok("разметку" in op["unchecked"][0]["items"][0]["why"],
              "причина названа вслух: " + op["unchecked"][0]["items"][0]["why"]))
res.append(ok("не удалось проверить 12" in S._o3_counts_line(op),
              "владельцу это третье число видно отдельно: " + S._o3_counts_line(op)))

# ═══ (5) ГОЛДЕН КЛАССА: фантом уходит, настоящая просрочка остаётся ═══════════════════════════
print("(5) голден класса «12 фантомов из 35»:")


class BR_MIX(BaseBR):
    """Два байка ДОСЛОВНО того же вида, что в переписи: у первого просрочка только из-за пустых
    клеток (фантом), у второго — настоящая, по значению."""
    ROWS = [
        bike("ADV 350CC BLACK PHUKET 5849", 3500, C_VAL(29000), C_VAL(29000), C_EMPTY(), C_EMPTY()),
        bike("NINJA 400CC PHUKET 6334", 40000, C_VAL(38000), C_EMPTY(), C_VAL(15000), C_VAL(5000)),
    ]
    SVC = [{"bike": r["name"], "current_km": 30000, "updated_at": "2026-08-01T00:00:00Z"}
           for r in ROWS]


mix = S._o3_overdue_scan(BR_MIX()).payload
res.append(ok([o["plate"] for o in mix["overdue"]] == ["6334"],
              "фантом 5849 ушёл из просрочек, настоящая просрочка 6334 осталась"))
res.append(ok([o["plate"] for o in mix["unmeasured"]] == ["5849"],
              f"неизмеренным назван 5849 — {[o['plate'] for o in mix['unmeasured']]}"))
res.append(ok(not any(o["plate"] == "6334" for o in mix["unmeasured"])
              and mix["counts"]["by_kind"]["gear"]["unmeasured"] == 0,
              "пустой редуктор мото 6334 НЕ попал даже в «не измерено»: регистра у него нет вовсе "
              "(иначе второе число распухло бы на нетрекаемых клетках — 9 таких в живом парке)"))
res.append(ok(mix["counts"]["overdue_bikes"] == 1 and mix["counts"]["unmeasured_bikes"] == 1,
              "счётчики: просрочен 1 байк, не измерен 1 — прежде оба были бы «просрочены»"))

# ═══ (6) ДОСКА: «решено» не говорится о неизмеренном ══════════════════════════════════════════
print("(6) доска нарядов: «✅ решено» ≠ «не измерено»:")
SENDS, EDITS = [], []
_MID = [9000]


class FakeSent:
    def __init__(s, m): s.message_id = m


class FakeBot:
    async def send_message(s, **kw): _MID[0] += 1; SENDS.append(kw); return FakeSent(_MID[0])
    async def edit_message_text(s, **kw): EDITS.append(kw)


class FakeCtx:
    def __init__(s): s.bot = FakeBot()


async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True,
                   reply_markup=None, **kw):
    _MID[0] += 1
    SENDS.append({"chat": chat_id, "text": text, "kb": reply_markup})
    return FakeSent(_MID[0])


_orig_send, _orig_sleep = S._send, asyncio.sleep
S._send = rec_send
async def _fake_sleep(t): pass
asyncio.sleep = _fake_sleep

mem = M.Memory(db_path=tempfile.mktemp(suffix=".db"))
S._MEMORY = mem
ctx = FakeCtx()


class BR_BEFORE(BaseBR):
    """ДО: у байка просрочка по ЗНАЧЕНИЮ — карточка на доске законна."""
    ROWS = [bike("ADV 350CC BLACK PHUKET 5849", 3500, C_VAL(20000), C_VAL(29000),
                 C_VAL(15000), C_VAL(5000))]
    SVC = [{"bike": ROWS[0]["name"], "current_km": 30000, "updated_at": "2026-08-01T00:00:00Z"}]


class BR_AFTER(BR_BEFORE):
    """ПОСЛЕ: те же клетки, но масло/ABS/фильтр оказались НЕ ИЗМЕРЕНЫ. Байк не починен."""
    ROWS = [bike("ADV 350CC BLACK PHUKET 5849", 3500, C_EMPTY(), C_VAL(29000),
                 C_TEXT("-"), C_EMPTY())]
    SVC = BR_BEFORE.SVC


class BR_FIXED(BR_BEFORE):
    """ПОЧИНЕН по-настоящему: все замены свежие, значения есть."""
    ROWS = [bike("ADV 350CC BLACK PHUKET 5849", 3500, C_VAL(29000), C_VAL(29000),
                 C_VAL(29000), C_VAL(29000))]
    SVC = BR_BEFORE.SVC


loop.run_until_complete(S.o3_post_board(ctx, BR_BEFORE()))
cards0 = mem.o3_cards(HQ)
res.append(ok("5849" in cards0, "карточка просроченного байка встала на доску"))
EDITS.clear()
stats = loop.run_until_complete(S._o3_board_sync(ctx, BR_AFTER()))
e5849 = [e for e in EDITS if e["message_id"] == cards0["5849"]]
res.append(ok(e5849 and "не измерено" in e5849[0]["text"],
              "карточка стала «🔎 не измерено», а НЕ «✅ решено»"))
res.append(ok(e5849 and "✅" not in e5849[0]["text"]
              and "решено, просрочек нет" not in e5849[0]["text"],
              "УТВЕРЖДЕНИЯ «✅ решено, просрочек нет» в карточке нет (само слово стоит только "
              "внутри отрицания «Это не «решено»» — оно и объясняет владельцу разницу)"))
res.append(ok("5849" in mem.o3_cards(HQ),
              "msg_id СОХРАНЁН: вопрос не закрыт, он сменил вид (прежде карточка забывалась)"))
res.append(ok(stats["gone"] == 0 and stats["unmeasured"] >= 1,
              f"в сводке это не «решено», а «не измерено» — gone={stats['gone']}, "
              f"unmeasured={stats['unmeasured']}"))
hdr = [e for e in EDITS if "Наряды · просрочки парка" in e.get("text", "")]
res.append(ok(hdr and "не измерено" in hdr[0]["text"],
              "заголовок доски называет второе число вслух"))
res.append(ok(hdr and "Просрочек нет 👍" in hdr[0]["text"] and "НЕ просрочка" in hdr[0]["text"],
              "«просрочек нет 👍» стоит РЯДОМ с «не измерено … это НЕ просрочка» — зелёный нуль не одинок"))
EDITS.clear()
stats2 = loop.run_until_complete(S._o3_board_sync(ctx, BR_FIXED()))
e_fixed = [e for e in EDITS if e["message_id"] == cards0["5849"]]
res.append(ok(e_fixed and "решено" in e_fixed[0]["text"] and stats2["gone"] == 1,
              "а НАСТОЯЩАЯ починка по-прежнему даёт «✅ решено» — ветка не сломана"))
res.append(ok("5849" not in mem.o3_cards(HQ), "и msg_id решённого забыт, как было"))

S._send = _orig_send
asyncio.sleep = _orig_sleep

# ═══ (7) ВЛАДЕЛЕЦ ВИДИТ ТРИ ЧИСЛА ════════════════════════════════════════════════════════════
print("(7) владелец видит три числа и невозможные значения:")
out = DB._g_overdue(BR3())
res.append(ok("просрочено 1" in out and "не измерено 4" in out and "не удалось проверить 0" in out,
              "в дайджесте владельца все три числа: " + out.splitlines()[0]))
res.append(ok("НЕ ИЗМЕРЕНО" in out and "ABS" in out and "Возд. фильтр" in out,
              "«не измерено» разложено ПО РЕГИСТРАМ поимённо"))
res.append(ok("не делалось" not in out,
              "прежняя формулировка «❗не делалось» из просрочек ушла — она и была слипанием"))
out_imp = DB._g_overdue(BR_IMP())
res.append(ok("КОТОРЫХ НЕ БЫВАЕТ" in out_imp and "-5000" in out_imp,
              "невозможные значения названы владельцу поимённо"))
res.append(ok("не исправлял" in out_imp,
              "и прямо сказано, что они НЕ исправлены: правка Лист1 — решение владельца"))
out_old = DB._g_overdue(BR_OLD())
res.append(ok("НЕ УДАЛОСЬ ПРОВЕРИТЬ" in out_old and "просрочено 0" in out_old,
              "слепой источник: владельцу сказано «не удалось проверить», а не «просрочек нет»"))
res.append(ok("не измерено 0" in out_old,
              "и «не измерено» тут ЧЕСТНЫЙ нуль: мы не знаем, что в клетке, и не выдумываем «пусто»"))

print(f"\nИТОГ: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
