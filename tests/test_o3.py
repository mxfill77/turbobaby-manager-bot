"""Моки O3 ступень 1 (доводка 02.07): скан с порогом «не делалось» (балласт убран) → o3_task/o3_card CRUD →
board «карточка-на-байк» (заголовок+счётчик, карточка+кнопка, троттл/RetryAfter, rescan без дублей,
«✅ в наряде»/«✅ решено», кап 30) → ABS-пометка (карточка+наряд) → конструктор-регресс (pick→vid→from→when→send)
→ паритет RU↔TH построчно во всех рендерах (фикс тайского 02.07: имя байка в TH, номер один раз, кнопки TH/RU).
Боевых тайцев/Telegram/Лист1 нет — всё мокнуто."""
import os, sys, asyncio, tempfile
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S
import memory as M
from telegram.error import RetryAfter

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []; loop = asyncio.new_event_loop()
HQ = S.O3_TEST_CHAT_ID

# --- РАЗМЕТКА КЛЕТОК (контракт `fleet_cell`, мост @79 от 10.08.2026) --------------------------
# Скан просит у моста разметку (`fleet(cells=True)`) и по ней РАЗЛИЧАЕТ пустую клетку, прочерк и
# настоящее число. Мок обязан повторять ЖИВОЙ формат запуска (§8 свода среды), иначе он проверяет
# несуществующий мост: без `cells` живой скан честно скажет «не удалось проверить» и не найдёт
# НИ ОДНОЙ просрочки. Форма снята с прода 10.08.2026:
#     значение {"state":"value","num":18302,"raw":"18302"} · пусто {"state":"empty","raw":""}
#     не-число {"state":"text","raw":"-"}
# ПЕРЕВОД ФИКСТУР: 0 в плоском поле означал здесь «замену не делали» — то есть ПУСТУЮ клетку;
# так и переведено. Единственная правка значения — ABS у NMAX (было 0): предмет ЭТОГО файла —
# механика доски (карточки, троттл, кап, паритет RU/TH), и байк должен остаться просроченным
# ПО-НАСТОЯЩЕМУ. Смысл «пустая клетка = не просрочка, а замер» закреплён отдельно —
# tests/test_overdue_cells.py.
_CELL_FIELDS = ("mileage", "oil_last_km", "gear_last_km", "abs_last_km", "airfilter_last_km")


def cells(row):
    """Строка парка → та же строка + `cells` в живой форме моста (0 → пусто, число → значение)."""
    mk = {}
    for f in _CELL_FIELDS:
        v = row.get(f) or 0
        mk[f] = {"state": "value", "num": v, "raw": str(v)} if v else {"state": "empty", "raw": ""}
    return dict(row, cells=mk)


def fleet_resp(rows, cells_wanted):
    """Ответ моста: разметка приезжает ТОЛЬКО по явной просьбе — как в проде."""
    return {"data": {"bikes": [cells(r) if cells_wanted else dict(r) for r in rows]}}


# --- mock bridge: knowledge_base fail → фоллбэк-интервалы (oil ск4000/мо5000, gear ск4000/мо None, abs 10000, air 20000)
_ROWS = [
    {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 3000,
     "oil_last_km": 24000, "gear_last_km": 27000, "abs_last_km": 5000, "airfilter_last_km": 5000},
    {"name": "NINJA 400CC PHUKET 6334", "status": "ДОМА", "mileage": 40000,
     "oil_last_km": 38000, "gear_last_km": 0, "abs_last_km": 25000, "airfilter_last_km": 10000},
    {"name": "PCX 160CC PHUKET 1111", "status": "ДОМА", "mileage": 5000,
     "oil_last_km": 4000, "gear_last_km": 4000, "abs_last_km": 0, "airfilter_last_km": 0},
]


class BR:
    def _call(s, a, **k): return {"ok": False}
    def fleet(s, cells=False): return fleet_resp(_ROWS, cells)
    def service_list(s): return {"items": [
        {"bike": "NMAX 155CC PHUKET 4255", "current_km": 30000},   # выше colH(3000) → max=30000 (тест max)
    ]}

# (1) скан: просрочки ПО ЗНАЧЕНИЮ клетки (10.08.2026: пустая клетка = «не измерено», не просрочка)
print("(1) _o3_overdue_scan (просрочка = значение, по которому срок вышел):")
scan = S._o3_overdue_scan(BR()); ov = (scan.payload or {}).get("overdue") or []
# КОНТРАКТ ЧИТАТЕЛЯ (08.08.2026): скан отдаёт ScanResult — пару «осмотрено/разобрано» и исход,
# а не голый {"overdue": […]}. Прежняя форма давала пустой список и на упавшем мосту, и на
# здоровом парке (перепись 2026-08-08-zero-on-parse-miss-census, §2 канал 16).
res.append(ok(scan.ok and scan.scanned == 3 and scan.parsed == 3,
              f"скан состоялся: {scan.say()}"))
res.append(ok(not hasattr(scan, "nobase"), "балласт-подсписок «нет базы» убран из скана"))
res.append(ok(len(ov) == 2, f"2 байка с просрочками (NMAX+NINJA), PCX нет — {len(ov)}"))
res.append(ok(not any("PCX" in o["bike"] for o in ov),
              "PCX: abs/air НЕ ИЗМЕРЕНЫ (клетки пусты), пробег 5000 < порогов → НЕ показан"))
res.append(ok([o["plate"] for o in (scan.payload or {}).get("unmeasured") or []] == ["1111"],
              "и PCX назван вслух в «не измерено» — молча он больше не исчезает"))
nm = [o for o in ov if "NMAX" in o["bike"]][0]
res.append(ok(nm["current_km"] == 30000, "NMAX текущий=max(colH,service_list)=30000"))
res.append(ok(ov[0] is nm and nm["items"][0]["kind"] == "abs"
              and nm["items"][0]["last"] == 5000 and nm["items"][0]["next"] == 15000
              and nm["items"][0]["over_km"] == 15000,
              "NMAX первый: ABS просрочен ПО ЗНАЧЕНИЮ 5000 (next=15000, пробег 30000)"))
res.append(ok([it["kind"] for it in nm["items"]] == ["abs", "airfilter", "oil"], "NMAX: abs>airfilter>oil (по over_km)"))
ninja = [o for o in ov if "NINJA" in o["bike"]][0]
res.append(ok([it["kind"] for it in ninja["items"]] == ["airfilter", "abs"]
              and all(it["last"] > 0 for it in ninja["items"]), "NINJA: airfilter+abs просрочены (база есть)"))
res.append(ok("gear" not in [it["kind"] for it in ninja["items"]], "NINJA мото: gear пропущен (interval None)"))

# (2) o3_task + o3_card CRUD
print("(2) o3_task + o3_card CRUD:")
mem = M.Memory(db_path=tempfile.mktemp(suffix=".db"))
tid = mem.o3_task_create(bike="NMAX 4255", plate="4255", kinds="oil,airfilter", from_where="office",
                         when_slot="now", status="sent", delivery_msg_id=555)
g = mem.o3_task_get(tid)
res.append(ok(g and g["bike"] == "NMAX 4255" and g["kinds"] == "oil,airfilter" and g["status"] == "sent"
              and g["delivery_msg_id"] == 555, "o3_task create+get round-trip"))
mem.o3_task_update(tid, status="new")
res.append(ok(mem.o3_task_get(tid)["status"] == "new", "o3_task update меняет status"))
mem.o3_card_set(HQ, "4255", 700); mem.o3_card_set(HQ, "4255", 701); mem.o3_card_set(HQ, "__header__", 699)
res.append(ok(mem.o3_cards(HQ) == {"4255": 701, "__header__": 699}, "o3_card set перезаписывает, o3_cards читает"))
mem.o3_card_del(HQ, "4255")
res.append(ok("4255" not in mem.o3_cards(HQ), "o3_card_del забывает карточку"))

# --- фейки Telegram ---
SENDS = []; EDITS = []; SLEEPS = []; _MID = [7000]
class FakeSent:
    def __init__(s, m): s.message_id = m
class FakeBot:
    async def send_message(s, **kw): _MID[0] += 1; SENDS.append(kw); return FakeSent(_MID[0])
    async def edit_message_text(s, **kw): EDITS.append(kw)
class FakeCtx:
    def __init__(s): s.bot = FakeBot()
class FakeChat:
    def __init__(s, c): s.id = c
class FakeMsg:
    def __init__(s, c, t): s.chat = FakeChat(c); s.message_thread_id = t; s.message_id = 555000
class FakeQ:
    def __init__(s, data, c=-100, t=None):
        s.data = data; s.message = FakeMsg(c, t); s.answers = []; s.edits = []
        s.from_user = type("U", (), {"username": "mech", "first_name": "M"})()
    async def answer(s, txt=None): s.answers.append(txt)
    async def edit_message_text(s, text=None, reply_markup=None, **kw): s.edits.append({"text": text, "kb": reply_markup})
class FakeUpd:
    def __init__(s, q): s.callback_query = q
FAIL_AT = set()   # номера ПОПЫТОК отправки, падающих RetryAfter (эмуляция флуд-контроля)
_ATT = [0]
async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, reply_markup=None, **kw):
    _ATT[0] += 1
    if _ATT[0] in FAIL_AT:
        raise RetryAfter(0)
    _MID[0] += 1; SENDS.append({"chat": chat_id, "topic": message_thread_id, "text": text, "kb": reply_markup})
    return FakeSent(_MID[0])
S._send = rec_send
_orig_sleep = asyncio.sleep
async def _fake_sleep(t): SLEEPS.append(t)
asyncio.sleep = _fake_sleep   # троттл/ретрай мгновенно; вызовы записываются (восстановим в конце)

def btn(kb): return kb.inline_keyboard[0][0] if kb else None

# (3) board «карточка-на-байк»: заголовок+счётчик+🔄, карточка+кнопка, троттл
print("(3) board карточка-на-байк:")
mem_b = M.Memory(db_path=tempfile.mktemp(suffix=".db")); S._MEMORY = mem_b
ctx = FakeCtx()
loop.run_until_complete(S.o3_post_board(ctx, BR()))
res.append(ok(len(SENDS) == 3, f"заголовок + 2 карточки = 3 сообщения — {len(SENDS)}"))
hdr = [s for s in SENDS if "Наряды · просрочки парка" in s["text"]]
res.append(ok(len(hdr) == 1 and "· 2 байков" in hdr[0]["text"], "заголовок с counter «просрочки парка · 2 байков»"))
res.append(ok(hdr and btn(hdr[0]["kb"]).callback_data == "o3:rescan", "заголовок с кнопкой [🔄 Обновить] (o3:rescan)"))
card_nm = [s for s in SENDS if "⚠️ 4255" in s["text"]]
res.append(ok(len(card_nm) == 1, "NMAX = своё сообщение-карточка"))
res.append(ok(card_nm and "ABS — просрочено 15000 км" in card_nm[0]["text"],
              "строка «просрочено N км» у ABS (ветка «❗ не делалось» убрана вместе с источником:"
              " неизмеренная клетка в наряд больше не попадает)"))
res.append(ok(card_nm and "Возд. фильтр — просрочено 5000 км" in card_nm[0]["text"], "строка «просрочено N км»"))
res.append(ok(card_nm and btn(card_nm[0]["kb"]).text == "🔧 สร้างใบสั่งงาน / Собрать наряд"
              and btn(card_nm[0]["kb"]).callback_data.startswith("o3:pick:"), "кнопка [🔧 …/ Собрать наряд] → o3:pick (TH+RU)"))
cards_db = mem_b.o3_cards(HQ)
res.append(ok(set(cards_db) == {"__header__", "4255", "6334"}, "msg_id заголовка и карточек в memory.db o3_card"))
res.append(ok(SLEEPS.count(S._O3_CARD_PAUSE) >= 2, f"троттл {S._O3_CARD_PAUSE}с между карточками"))

# (4) rescan: existing → editMessageText, дублей нет
print("(4) rescan без дублей:")
n_sends = len(SENDS); EDITS.clear()
loop.run_until_complete(S._o3_refresh_board(ctx, BR()))
res.append(ok(len(SENDS) == n_sends, "повторный синк НЕ шлёт новых сообщений (нет дублей)"))
res.append(ok(len(EDITS) == 3 and {e["message_id"] for e in EDITS} == set(cards_db.values()),
              "заголовок + обе карточки обновлены editMessageText"))

# (5) байк ушёл в наряд → карточка «✅ в наряде» без кнопки
print("(5) пометка «в наряде»:")
mem_b.o3_task_create(bike="NMAX 155CC PHUKET 4255", plate="4255", kinds="abs", status="sent")
EDITS.clear()
loop.run_until_complete(S._o3_refresh_board(ctx, BR()))
e_nm = [e for e in EDITS if e["message_id"] == cards_db["4255"]]
res.append(ok(e_nm and "✅ в наряде" in e_nm[0]["text"] and e_nm[0].get("reply_markup") is None,
              "карточка 4255 → «✅ в наряде», кнопка убрана"))

# (6) байк ушёл из просрочки → «✅ решено» (след остаётся), msg_id забыт
print("(6) пометка «решено»:")
class BR2(BR):   # NMAX обслужили (база свежая), NINJA всё ещё просрочен
    def fleet(s, cells=False): return fleet_resp([
        {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 3000,
         "oil_last_km": 30000, "gear_last_km": 30000, "abs_last_km": 30000, "airfilter_last_km": 30000},
        {"name": "NINJA 400CC PHUKET 6334", "status": "ДОМА", "mileage": 40000,
         "oil_last_km": 38000, "gear_last_km": 0, "abs_last_km": 25000, "airfilter_last_km": 10000},
    ], cells)
EDITS.clear()
loop.run_until_complete(S._o3_refresh_board(ctx, BR2()))
e_done = [e for e in EDITS if e["message_id"] == cards_db["4255"]]
res.append(ok(e_done and "✅ 4255 — решено, просрочек нет" in e_done[0]["text"], "карточка 4255 → «✅ решено»"))
left = mem_b.o3_cards(HQ)
res.append(ok("4255" not in left and "6334" in left, "msg_id решённого забыт, NINJA остался"))
res.append(ok(any("· 1 байков" in e.get("text", "") for e in EDITS), "заголовок-счётчик обновился (2 → 1)"))

# (7) 35 просрочек: кап 30 карточек + хвост в заголовке + RetryAfter-ретрай → все доставлены
print("(7) кап 30 + троттл/RetryAfter на потоке карточек:")
# Текущий пробег байков различаем СВОИМ одометром («обслуживание».current_km), а не кол.H:
# с 31.07.2026 (класс-фикс 4957, корень 4) кол.H = пробег ПРИ ПОКУПКЕ и в текущий не входит вовсе,
# поэтому порядок «худшие сверху» и хвост сверх капа должны задаваться реальным источником.
class BR35:
    def _call(s, a, **k): return {"ok": False}
    def fleet(s, cells=False): return fleet_resp([
        {"name": f"NMAX 155CC PHUKET {5100 + i}", "status": "ДОМА", "mileage": 3000,
         "oil_last_km": 1000, "gear_last_km": 19000, "abs_last_km": 15000, "airfilter_last_km": 5000}
        for i in range(35)], cells)
    def service_list(s): return {"items": [
        {"bike": f"NMAX 155CC PHUKET {5100 + i}", "service_type": "oil",
         "current_km": 20000 + i * 10, "updated_at": "2026-07-30T00:00:00Z"}
        for i in range(35)]}
mem_c = M.Memory(db_path=tempfile.mktemp(suffix=".db")); S._MEMORY = mem_c
SENDS.clear(); SLEEPS.clear(); _ATT[0] = 0
FAIL_AT.update({4, 12, 25})   # три отправки ловят флуд-контроль с первой попытки
loop.run_until_complete(S.o3_post_board(ctx, BR35()))
FAIL_AT.clear()
res.append(ok(len(SENDS) == 31, f"кап: заголовок + 30 карточек (не 35) — {len(SENDS)}"))
hdr35 = [s for s in SENDS if "Наряды · просрочки парка · 35 байков" in s["text"]]
res.append(ok(bool(hdr35), "counter=35 в заголовке"))
res.append(ok(hdr35 and "…ещё 5 вне карточек: " in hdr35[0]["text"] and "5100" in hdr35[0]["text"],
              "хвост сверх капа — строкой в заголовке (5 худших НЕ потеряны)"))
res.append(ok(len(mem_c.o3_cards(HQ)) == 31, "все 30 карточек + заголовок персистнуты (RetryAfter пережит)"))
res.append(ok(SLEEPS.count(S._O3_CARD_PAUSE) >= 30 and any(t >= 1 for t in SLEEPS),
              "троттл на каждой карточке + ожидание окна RetryAfter"))

# (8) ABS → чистка цилиндров: пометка в карточке + обязательная строка в наряде (RU+TH)
print("(8) ABS-правило:")
res.append(ok("⚠️ чистка цилиндров обязательна" in card_nm[0]["text"]
              and "ล้างกระบอกสูบ" in card_nm[0]["text"], "карточка: короткая пометка у строки ABS (RU+TH)"))
d_abs = {"bike": "NMAX 155CC PHUKET 4255", "plate": "4255", "kinds": ["abs", "oil"],
         "from_where": "office", "when": "now"}
th_l, ru_l = S._o3_naryad_lines(d_abs)
res.append(ok("⚠️ При замене ABS: чистка цилиндров ОБЯЗАТЕЛЬНА" in ru_l
              and "⚠️ เปลี่ยนน้ำมัน ABS: ต้องทำความสะอาดกระบอกสูบด้วย" in th_l, "наряд с ABS: строка чистки RU+TH"))
th_n, ru_n = S._o3_naryad_lines({**d_abs, "kinds": ["oil"]})
res.append(ok(not any("ABS" in x for x in ru_n) and not any("กระบอกสูบ" in x for x in th_n),
              "наряд без ABS: строки чистки НЕТ"))

# (9) конструктор-регресс: pick → vid тоггл → from → when → send (flow не тронут)
print("(9) конструктор наряда (регресс):")
S._MEMORY = mem_b
tok = S._o3_put({"bike": "NMAX 155CC PHUKET 4255", "plate": "4255", "current_km": 30000,
                 "overdue_kinds": ["oil", "abs"], "kinds": ["oil", "abs"], "from_where": None, "when": None})
SENDS.clear()
q = FakeQ(f"o3:pick:{tok}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q), ctx, BR()))
res.append(ok(any("Выбери виды" in s["text"] for s in SENDS), "pick → конструктор (выбор видов) новым сообщением"))
q2 = FakeQ(f"o3:vid:{tok}:oil")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q2), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["kinds"] == ["abs"], "vid тоггл снял oil (остался abs)"))
q3 = FakeQ(f"o3:step:{tok}:from")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q3), ctx, BR()))
res.append(ok(any("Откуда" in e["text"] for e in q3.edits), "step:from → шаг «откуда»"))
q4 = FakeQ(f"o3:from:{tok}:office")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q4), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["from_where"] == "office" and any("Когда" in e["text"] for e in q4.edits), "from=office → шаг «когда»"))
q5 = FakeQ(f"o3:when:{tok}:now")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q5), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["when"] == "now" and any("Проверь наряд" in e["text"] for e in q5.edits), "when=now → предпросмотр"))

# (10) send: наряд RU+TH с ABS-строкой + o3_task + подтверждение
print("(10) отправка наряда (с ABS):")
SENDS.clear()
q6 = FakeQ(f"o3:send:{tok}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q6), ctx, BR()))
naryad = [s for s in SENDS if "Наряд на ТО" in s["text"]]
res.append(ok(len(naryad) == 1, "send → наряд запощен (1 сообщение)"))
res.append(ok("работы: ABS" in naryad[0]["text"] and "забрать: в офисе" in naryad[0]["text"]
              and "когда: сейчас" in naryad[0]["text"], "текст наряда RU: работы/откуда/когда"))
res.append(ok("งาน: น้ำมัน ABS" in naryad[0]["text"] and "รับรถ: ที่ออฟฟิศ" in naryad[0]["text"], "текст наряда TH"))
res.append(ok("⚠️ При замене ABS: чистка цилиндров ОБЯЗАТЕЛЬНА" in naryad[0]["text"]
              and "ต้องทำความสะอาดกระบอกสูบ" in naryad[0]["text"], "наряд содержит ABS-строку чистки RU+TH"))
res.append(ok(any("Наряд отправлен" in e["text"] for e in q6.edits), "конструктор → подтверждение (след)"))
res.append(ok(any(t["plate"] == "4255" and t["kinds"] == "abs" for t in mem_b.o3_tasks_active()),
              "o3_task(sent) записан с выбранным видом (abs)"))

# (11) back → чистая отмена
print("(11) back-отмена:")
tok2 = S._o3_put({"bike": "X 1", "plate": "1", "overdue_kinds": ["oil"], "kinds": ["oil"], "from_where": None, "when": None})
SENDS.clear()
qb = FakeQ(f"o3:back:{tok2}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qb), ctx, BR()))
res.append(ok(not any("Наряд на ТО" in s.get("text", "") for s in SENDS) and any("отменён" in e["text"] for e in qb.edits),
              "back → отменено, ничего не отправлено"))

# (12) устойчивость: неизвестный токен / rescan (усыновление заголовка) — не падает
print("(12) устойчивость префикса o3:")
qg = FakeQ("o3:bogus:999999")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qg), ctx, BR()))
res.append(ok(qg.answers and any("устарел" in e["text"] for e in qg.edits), "неизвестный токен → «устарел», не падает"))
qr = FakeQ("o3:rescan", c=HQ)
loop.run_until_complete(S.handle_o3_button(FakeUpd(qr), ctx, BR()))
res.append(ok(qr.answers == ["🔄"], "rescan → q.answer, не падает"))
res.append(ok(mem_b.o3_cards(HQ).get("__header__") == 555000, "rescan усыновил msg_id заголовка (переживает рестарт)"))

# (13) пустой парк без просрочек → карточек нет, заголовок «Просрочек нет»
print("(13) просрочек нет:")
class BR0(BR):
    def fleet(s, cells=False): return fleet_resp([
        {"name": "PCX 160CC PHUKET 1111", "status": "ДОМА", "mileage": 5000,
         "oil_last_km": 4000, "gear_last_km": 4000, "abs_last_km": 0, "airfilter_last_km": 0}], cells)
    def service_list(s): return {"items": []}
mem_0 = M.Memory(db_path=tempfile.mktemp(suffix=".db")); S._MEMORY = mem_0
SENDS.clear()
loop.run_until_complete(S.o3_post_board(ctx, BR0()))
res.append(ok(len(SENDS) == 1 and "Просрочек нет 👍" in SENDS[0]["text"], "0 просрочек → только заголовок, карточек нет"))

# (14) паритет RU↔TH построчно (фикс тайского 02.07): TH-блок = зеркало RU во ВСЕХ рендерах
print("(14) паритет RU/TH построчно (все рендеры):")
import re
CYR = re.compile(r"[А-Яа-яЁё]")
THAI = re.compile(r"[฀-๿]")
def blocks(text):
    th = [l for l in text.split("🇹🇭", 1)[1].split("🇷🇺")[0].split("\n") if l.strip() and set(l.strip()) != {"─"}]
    ru = [l for l in text.split("🇷🇺", 1)[1].split("\n") if l.strip()]
    return th, ru
d14 = {"bike": "NMAX 155CC PHUKET 4255", "plate": "4255", "current_km": 30000,
       "overdue_kinds": ["abs", "oil"], "kinds": ["abs", "oil"], "from_where": "office", "when": "now"}
LBL = "4255 NMAX 155CC PHUKET"
renders = {
    "карточка board":  S._o3_card_render(nm, set())[0],
    "заголовок board": S._o3_header_render(2, ["1234", "5678"])[0],
    "шаг1 виды":       S._o3_step_vids(d14, 1)[0],
    "шаг2 откуда":     S._o3_step_from(d14, 1)[0],
    "шаг3 когда":      S._o3_step_when(d14, 1)[0],
    "шаг4 предпросмотр": S._o3_step_confirm(d14, 1)[0],
}
for label, text in renders.items():
    th_b, ru_b = blocks(text)
    res.append(ok(len(th_b) == len(ru_b), f"{label}: строк TH == строк RU ({len(th_b)}/{len(ru_b)})"))
    res.append(ok(not CYR.search("\n".join(th_b)), f"{label}: TH-блок без кириллицы"))
for label in ("карточка board", "шаг1 виды", "шаг2 откуда", "шаг3 когда", "шаг4 предпросмотр"):
    th_b, ru_b = blocks(renders[label])
    res.append(ok(LBL in "\n".join(th_b) and LBL in "\n".join(ru_b),
                  f"{label}: полное имя байка в ОБОИХ блоках"))
    res.append(ok("\n".join(th_b).count("4255") == 1 and "\n".join(ru_b).count("4255") == 1,
                  f"{label}: номер один раз в каждом блоке (дубля нет)"))
for label, text in renders.items():   # каждая кнопка двуязычна: тайский + (кириллица или общий 🔄-стиль)
    kb14 = {"карточка board": S._o3_card_render(nm, set())[1], "заголовок board": S._o3_header_render(2, [])[1],
            "шаг1 виды": S._o3_step_vids(d14, 1)[1], "шаг2 откуда": S._o3_step_from(d14, 1)[1],
            "шаг3 когда": S._o3_step_when(d14, 1)[1], "шаг4 предпросмотр": S._o3_step_confirm(d14, 1)[1]}[label]
    btns = [b for row in kb14.inline_keyboard for b in row]
    res.append(ok(all(THAI.search(b.text) for b in btns), f"{label}: все кнопки ({len(btns)}) с тайским"))
th_n14, ru_n14 = S._o3_naryad_lines(d14)
res.append(ok(len(th_n14) == len(ru_n14) and th_n14[0] == LBL and ru_n14[0] == LBL
              and not CYR.search("\n".join(th_n14)),
              "наряд: строк TH == RU, байк = «номер имя» один раз, TH без кириллицы"))
qs14 = FakeQ("o3:pick:999777")   # несуществующий токен → «устарел» теперь тоже двуязычный
loop.run_until_complete(S.handle_o3_button(FakeUpd(qs14), ctx, BR()))
res.append(ok(qs14.edits and "ใบสั่งงานหมดอายุ" in qs14.edits[0]["text"] and "устарел" in qs14.edits[0]["text"],
              "«наряд устарел»: TH-блок добавлен (двуязычно)"))

# (15) фикс «/o3board молчит» (02.07): stats синка для сводки владельцу + протухший q.answer не валит кнопку
print("(15) фикс «/o3board молчит»:")
mem_f = M.Memory(db_path=tempfile.mktemp(suffix=".db")); S._MEMORY = mem_f
SENDS.clear()
st1 = loop.run_until_complete(S.o3_post_board(ctx, BR()))
res.append(ok({k: st1.get(k) for k in ("overdue", "cards", "new", "gone")}
              == {"overdue": 2, "cards": 2, "new": 2, "gone": 0},
              f"первый пост: stats {{overdue:2, cards:2, new:2, gone:0}} — {st1}"))
res.append(ok(st1.get("unmeasured") == 2 and st1.get("unmeasured_bikes") == 1
              and "не измерено 2" in st1.get("counts_line", ""),
              "и сводка НЕСЁТ второе число отдельно (PCX: две неизмеренные клетки) — "
              "прежде оно молча пропадало между «просрочено» и «решено»"))
n15 = len(SENDS)
st2 = loop.run_until_complete(S.o3_post_board(ctx, BR()))
res.append(ok(st2 and st2["new"] == 0 and st2["cards"] == 2 and len(SENDS) == n15,
              f"повторный синк: new=0 (всё эдиты-на-месте, сводка честно скажет «обновлены на месте») — {st2}"))
class DeadAnswerQ(FakeQ):   # колбэк протух за долгим синком (реальный кейс 20:19:49 02.07)
    async def answer(s, txt=None):
        raise Exception("Query is too old and response timeout expired or query id is invalid")
tok15 = S._o3_put({"bike": "NMAX 155CC PHUKET 4255", "plate": "4255", "current_km": 30000,
                   "overdue_kinds": ["oil", "abs"], "kinds": ["oil", "abs"], "from_where": None, "when": None})
SENDS.clear()
qd = DeadAnswerQ(f"o3:pick:{tok15}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qd), ctx, BR()))
res.append(ok(any("Выбери виды" in s["text"] for s in SENDS),
              "протухший q.answer НЕ валит pick — конструктор всё равно открыт"))
qd2 = DeadAnswerQ("o3:rescan", c=HQ)
loop.run_until_complete(S.handle_o3_button(FakeUpd(qd2), ctx, BR()))
res.append(ok(mem_f.o3_cards(HQ).get("__header__") == 555000,
              "протухший q.answer НЕ валит rescan — заголовок усыновлён, синк прошёл"))

asyncio.sleep = _orig_sleep
loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
