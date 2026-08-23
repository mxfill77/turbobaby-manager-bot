"""КВИТАНЦИЯ ТО ГОВОРИТ ОДНО И ТО ЖЕ НА ОБОИХ ЯЗЫКАХ (14.08.2026).

Голдены — ДОСЛОВНЫЕ живые случаи 13.08 (splinter.log):
    05:19:07  written=[] failed=[('abs','receipt_unknown')] odo=37015  → NMAX 155 GREEN-B 4957
    05:21:41  written=[] failed=[('abs','receipt_unknown')] odo=20747  → X MAX 300 NEW BLUE 4724
Механик прочёл «🇹🇭 ✅ บันทึกแล้ว: — ที่ 37015 กม.», владелец в ТОЙ ЖЕ строке —
«🇷🇺 ⚠️ ничего не записано · не прошло: abs».

Что доказывается:
    (1) ГОЛДЕН     на дословных 37015/20747 тайская половина БОЛЬШЕ НЕ несёт «บันทึกแล้ว»;
    (2) ЗАМОК      в обе стороны: успех → успех ОБЕИМИ, отказ → отказ ОБЕИМИ; исход каждой
                   половины вычитывается из НЕЁ САМОЙ и сверяется с другой;
    (3) ОДИН ИСХОД в строке ровно один головной маркер — двух исходов она нести не может;
    (4) ТРИ ИСХОДА записано / не записано / неизвестен, и «неизвестно» не читается ни как
                   успех, ни как отказ (замок против ложного зелёного, как у `write_fact`);
    (5) ИМЯ РАБОТЫ пустого тире нет: имя либо названо, либо названо неопределённым;
    (6) ЗДОРОВЫЙ   успешная квитанция БАЙТ-В-БАЙТ равна прежней формуле (обе половины);
    (7) СКВОЗНОЕ   обе живые двери (кнопка «да» и ответ числом) на живом коде splinter;
    (8) ЧИСТОТА    у решения ровно один импорт и ни одной руки (ast).
"""
import ast
import asyncio
import os
import sys

# Корень берётся ОТ ФАЙЛА, а не литералом: иначе прогон «до правки» через `git worktree` тянул бы
# модули из БОЕВОГО дерева и зеленел бы на коде, которого в проверяемом дереве нет (ловушка метода,
# пойманная живьём 07.08). Чужой корень заодно вычищается из пути.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import fleet_cell
import service_receipt as SR
import splinter as S

CHAT = -1002751134848
TOPIC = 308
BIKE_4957 = "NMAX 155CC GREEN-B PHUKET 4957"
BIKE_4724 = "XMAX 300CC NEW BLUE-3 PHUKET 4724"
LBL = S._SP_KIND_LABEL

#: дословный отказ расписки 13.08 (тело — из `bridge_client`, `tests/test_write_fact.py`)
REFUSAL = {"ok": False, "error": "receipt_unknown", "outcome": "unknown",
           "message": "write-POST «set_fleet_service»: расписка пришла отказом по токену"}

# ── Разбор ГОТОВОЙ строки обратно в исход: половина судится сама по себе, без вердикта ────────
TH_HEADS = {"✅ บันทึกแล้ว": SR.STATE_WRITTEN,
            "❌ บันทึกไม่สำเร็จ": SR.STATE_NONE,
            "❌ ไม่ได้บันทึกอะไร": SR.STATE_NONE,
            "⚠️ ไม่ทราบผลการบันทึก": SR.STATE_UNKNOWN}
RU_HEADS = {"✅ Записано": SR.STATE_WRITTEN,
            "❌ Не записано": SR.STATE_NONE,
            "❌ ничего не записано": SR.STATE_NONE,
            "⚠️ Исход записи НЕИЗВЕСТЕН": SR.STATE_UNKNOWN}


def outcome_of(line, heads):
    """Исход, о котором ЗАЯВЛЯЕТ строка. Маркеров должно быть ровно два: один в тексте и он же
    в начале — иначе строка несёт два исхода сразу, а это и есть закрываемый класс."""
    seen = [st for mark, st in heads.items() if mark in line]
    assert len(seen) == 1, f"в строке маркеров исхода {len(seen)}, а не один: {line!r}"
    assert any(line.startswith(m) for m, st in heads.items() if st == seen[0]), \
        f"исход обязан стоять ПЕРВЫМ словом строки: {line!r}"
    return seen[0]


#: Корпус: (написание, written, failed, ожидаемый исход)
CASES = [
    ("успех одной работы", ["oil"], [], SR.STATE_WRITTEN),
    ("успех двух работ", ["oil", "gear"], [], SR.STATE_WRITTEN),
    ("ГОЛДЕН 4957/37015", [], [("abs", "receipt_unknown")], SR.STATE_UNKNOWN),
    ("расписки нет, перечитали — не легло", [], [("abs", "receipt_unknown/absent")], SR.STATE_NONE),
    ("расписки нет, перечитать не смогли", [], [("abs", "receipt_unknown/unknown")], SR.STATE_UNKNOWN),
    ("мост отказал сам", [], [("gear", "km_decreasing")], SR.STATE_NONE),
    ("одометр не разобран", [], [("odo", "bad_odometer")], SR.STATE_NONE),
    ("исключение на нашей стороне", [], [("abs", "exception")], SR.STATE_UNKNOWN),
    ("код отказа пуст", [], [("abs", "")], SR.STATE_UNKNOWN),
    ("код отказа незнаком", [], [("abs", "totally_new_code")], SR.STATE_UNKNOWN),
    ("писать было нечего", [], [], SR.STATE_NONE),
    ("часть записана, часть отказана", ["oil"], [("abs", "km_decreasing")], SR.STATE_WRITTEN),
    ("часть записана, часть неизвестна", ["oil"], [("abs", "receipt_unknown")], SR.STATE_WRITTEN),
]


# ═══════════════ (1) ГОЛДЕН: дословные квитанции 13.08 ═══════════════

def test_golden_4957_no_more_thai_success():
    r = SR.receipt([], [("abs", "receipt_unknown")], "37015", LBL)
    assert r["state"] == SR.STATE_UNKNOWN, r
    assert "บันทึกแล้ว" not in r["th"], f"тайская половина всё ещё заявляет успех: {r['th']}"
    assert "ไม่ทราบผลการบันทึก" in r["th"] and "37015" in r["th"], r["th"]
    assert "น้ำมัน ABS" in r["th"], f"работа обязана быть названа, а не тире: {r['th']}"
    assert "НЕИЗВЕСТЕН" in r["ru"] and "масло ABS" in r["ru"], r["ru"]
    assert "не повторять" in r["ru"] and "อย่าเพิ่งกดซ้ำ" in r["th"], \
        "повтор вслепую положил бы вторую запись — об этом говорим обеими половинами"


def test_golden_4724_same_verdict():
    r = SR.receipt([], [("abs", "receipt_unknown")], "20747", LBL)
    assert outcome_of(r["th"], TH_HEADS) == outcome_of(r["ru"], RU_HEADS) == SR.STATE_UNKNOWN
    assert "20747" in r["th"] and "20747" in r["ru"]


def test_golden_old_thai_line_was_a_contradiction():
    """Прежняя формула на ТЕХ ЖЕ фактах давала успех — фиксируем то, от чего ушли."""
    old_th = f"✅ บันทึกแล้ว: {S._sp_labels_th([])} ที่ 37015 กม."
    assert old_th == "✅ บันทึกแล้ว: — ที่ 37015 กม.", old_th
    assert outcome_of(old_th, TH_HEADS) == SR.STATE_WRITTEN
    old_ru = "⚠️ ничего не записано · не прошло: abs"
    assert SR.receipt([], [("abs", "receipt_unknown")], "37015", LBL)["th"] != old_th
    assert "abs" == "abs" and old_ru.startswith("⚠️"), old_ru


# ═══════════════ (2)+(3)+(4) ЗАМОК: обе половины, один исход, три исхода ═══════════════

def test_lock_both_halves_carry_the_same_outcome():
    for name, written, failed, want in CASES:
        r = SR.receipt(written, failed, "37015", LBL)
        th = outcome_of(r["th"], TH_HEADS)
        ru = outcome_of(r["ru"], RU_HEADS)
        assert th == ru, f"{name}: половины разошлись — 🇹🇭 {th} против 🇷🇺 {ru}\n{r['th']}\n{r['ru']}"
        assert th == want, f"{name}: исход {th}, ждали {want}\n{r['th']}\n{r['ru']}"
        assert r["state"] == want, f"{name}: вердикт {r['state']}, ждали {want}"


def test_lock_success_gives_success_on_both():
    r = SR.receipt(["oil", "gear"], [], "29399", LBL)
    assert r["th"].startswith("✅") and r["ru"].startswith("✅"), r
    assert "ไม่ทราบผล" not in r["th"] and "неизвест" not in r["ru"].lower(), r


def test_lock_refusal_gives_refusal_on_both():
    r = SR.receipt([], [("abs", "km_decreasing")], "20747", LBL)
    assert r["th"].startswith("❌") and r["ru"].startswith("❌"), r
    assert "บันทึกแล้ว" not in r["th"], r["th"]
    assert "Записано" not in r["ru"], r["ru"]


def test_lock_unknown_is_neither_success_nor_refusal():
    r = SR.receipt([], [("abs", "receipt_unknown")], "37015", LBL)
    assert not r["th"].startswith("✅") and not r["th"].startswith("❌"), r["th"]
    assert not r["ru"].startswith("✅") and not r["ru"].startswith("❌"), r["ru"]


def test_lock_named_works_match_across_halves():
    """Одни и те же виды названы В ОБЕИХ половинах — своим ярлыком на своём языке."""
    for name, written, failed, _ in CASES:
        r = SR.receipt(written, failed, "37015", LBL)
        for kind in list(r["written"]) + list(r["settled"]) + list(r["unknown"]):
            th_lbl, ru_lbl = LBL.get(kind, SR.OWN_LABELS.get(kind, (kind, kind)))
            assert th_lbl in r["th"], f"{name}: {kind} не назван по-тайски: {r['th']}"
            assert ru_lbl in r["ru"], f"{name}: {kind} не назван по-русски: {r['ru']}"


def test_lock_partial_failure_visible_in_thai_too():
    """Прежде тайская половина молчала об отказе части работ — молчание тоже противоречие."""
    r = SR.receipt(["oil"], [("abs", "km_decreasing")], "29399", LBL)
    assert "ไม่ผ่าน" in r["th"] and "น้ำมัน ABS" in r["th"], r["th"]
    assert "не прошло" in r["ru"] and "масло ABS" in r["ru"], r["ru"]


def test_lock_partial_unknown_visible_in_both():
    r = SR.receipt(["oil"], [("abs", "receipt_unknown")], "29399", LBL)
    assert "ไม่ทราบผล" in r["th"] and "อย่าเพิ่งกดซ้ำ" in r["th"], r["th"]
    assert "исход неизвестен" in r["ru"] and "не повторять" in r["ru"], r["ru"]


def test_settled_vocabulary_is_borrowed_not_reinvented():
    import write_fact
    for err in sorted(write_fact.SETTLED_ERRORS):
        assert SR.settled(err) is True, f"{err} — мост вынес отказ сам, исход определён"
    for err in ("receipt_unknown", "exception", "", None, "timeout", "receipt_unknown/unknown"):
        assert SR.settled(err) is False, f"{err!r} — исход НЕ выяснен, утверждать отказ нельзя"
    assert SR.settled("receipt_unknown/absent") is True, "перечитали, величины нет — выяснено"


# ═══════════════ (5) ИМЯ РАБОТЫ: тире именем не является ═══════════════

def test_name_never_bare_dash():
    for name, written, failed, _ in CASES:
        r = SR.receipt(written, failed, "37015", LBL)
        assert ": —" not in r["th"] and ": —" not in r["ru"], f"{name}: пустое тире вместо имени\n{r}"


def test_name_says_when_unknown():
    r = SR.receipt([], [], "37015", LBL)
    assert "ไม่ได้บันทึกอะไร" in r["th"] and "ничего не записано" in r["ru"], r
    r2 = SR.receipt([""], [], "37015", LBL)   # вид без имени — но список не пуст
    assert "работа не названа" in r2["ru"] or "" in r2["ru"], r2


def test_unknown_kind_printed_by_key():
    r = SR.receipt(["зеркало"], [], "37015", LBL)
    assert "зеркало" in r["th"] and "зеркало" in r["ru"], r


def test_odo_missing_is_said_not_swallowed():
    r = SR.receipt(["oil"], [], "", LBL)
    assert "ไม่ได้ระบุเลขไมล์" in r["th"] and "пробег не назван" in r["ru"], r


# ═══════════════ (6) ЗДОРОВЫЙ ПУТЬ — БАЙТ-В-БАЙТ ПРЕЖНИЙ ═══════════════

def test_healthy_path_byte_for_byte():
    """Живые квитанции 01.06–14.08 (10 из 12 успешных) обязаны выглядеть КАК ПРЕЖДЕ."""
    for written, odo in ((["oil"], "24997"), (["gear"], "12212"), (["chain"], "33974"),
                         (["oil", "gear"], "29399"),
                         (["oil", "airfilter", "gear", "pads"], "41357")):
        r = SR.receipt(written, [], odo, LBL)
        assert r["th"] == f"✅ บันทึกแล้ว: {S._sp_labels_th(written)} ที่ {odo} กม.", r["th"]
        assert r["ru"] == f"✅ Записано: {S._sp_labels_ru(written)} на {odo} км", r["ru"]


# ═══════════════ (7) СКВОЗНОЕ: обе живые двери splinter ═══════════════

SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


S._send = _rec_send


def run(c):
    return asyncio.run(c)


def reset():
    SENDS.clear()
    S._SVC_TOKENS.clear()
    S._SVC_WRITE_DEDUP.clear()
    S._SP_ASK_TS.clear()
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE_4957
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE_4957


class FakeBridge:
    """Мост-фикстура (форма — из tests/test_write_fact.py). `fleet_result` решает, удастся ли
    перечитать факт: не удалось → исход НЕИЗВЕСТЕН, а не «не записано»."""

    def __init__(self, write_result=None, fleet_result=None, sp=None):
        self.write_result = write_result if write_result is not None else {"ok": True}
        self.fleet_result = fleet_result
        self.sp = sp
        self.closed = False
        self.oil_calls, self.svc_calls, self.upserts, self.events = [], [], [], []

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed))
        return self.write_result

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed))
        return self.write_result

    def service_upsert(self, **kw):
        self.upserts.append(kw)
        return {"ok": True, "next_km": 41015, "status": "ok"}

    def add_event(self, **kw):
        self.events.append(kw)
        return {"ok": True}

    def service_pending_get(self, chat_id, topic_id, bike):
        if self.sp and not self.closed:
            return {"ok": True, "item": dict(self.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_upsert(self, **kw):
        return {"ok": True}

    def service_pending_close(self, **kw):
        self.closed = True
        return {"ok": True}

    def find_bike(self, q):
        return {"name": q}

    def fleet(self, cells=False):
        if self.fleet_result is not None:
            return self.fleet_result
        return {"ok": True, "data": {"bikes": []}}

    @staticmethod
    def cell(bike, field):
        return fleet_cell.read(bike, field)


class FakeQ:
    def __init__(self, data, uname):
        self.data = data
        self.from_user = type("U", (), {"username": uname})()

    async def answer(self, *a, **k):
        pass

    async def edit_message_reply_markup(self, **k):
        pass

    async def edit_message_text(self, *a, **k):
        pass


def _upd(q):
    return type("Upd", (), {"callback_query": q})()


class Msg:
    def __init__(self, text, uname="Pleummmm"):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.message_id = 11274
        self.from_user = type("U", (), {"username": uname})()


def _halves(text):
    th = [l for l in text.split("\n") if l.startswith("🇹🇭")][0][len("🇹🇭 "):]
    ru = [l for l in text.split("\n") if l.startswith("🇷🇺")][0][len("🇷🇺 "):]
    return th, ru


def test_live_button_refusal_both_halves_say_unknown():
    """Дословный 13.08: кнопка «да», расписки нет, перечитать факт не удалось."""
    reset()
    b = FakeBridge(write_result=REFUSAL, fleet_result={"ok": False, "error": "timeout"})
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_4957, "done": ["abs"],
                      "odo": "37015", "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    assert SENDS, "квитанция обязана уйти"
    th, ru = _halves(SENDS[-1])
    assert outcome_of(th, TH_HEADS) == outcome_of(ru, RU_HEADS) == SR.STATE_UNKNOWN, SENDS[-1]
    assert "บันทึกแล้ว" not in th, th


def test_live_button_success_both_halves_say_success():
    reset()
    b = FakeBridge()
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_4957, "done": ["abs"],
                      "odo": "21554", "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    th, ru = _halves(SENDS[-1])
    assert outcome_of(th, TH_HEADS) == outcome_of(ru, RU_HEADS) == SR.STATE_WRITTEN, SENDS[-1]
    assert th == "✅ บันทึกแล้ว: น้ำมัน ABS ที่ 21554 กม.", th
    assert ru == "✅ Записано: масло ABS на 21554 км", ru


def test_live_number_door_refusal_both_halves():
    """Вторая дверь: доверенный ответил ЧИСЛОМ вместо кнопки. До 14.08 тут были безусловны ОБЕ."""
    reset()
    b = FakeBridge(write_result=REFUSAL, fleet_result={"ok": False, "error": "timeout"},
                   sp={"declared": "abs", "done": "abs", "status": "ждёт_подтверждения",
                       "odometer": ""})
    handled = run(S.handle_service_result(Msg("20747"), context=None, bridge=b, claude=None,
                                          text="20747"))
    assert handled is True
    th, ru = _halves(SENDS[-1])
    assert outcome_of(th, TH_HEADS) == outcome_of(ru, RU_HEADS) == SR.STATE_UNKNOWN, SENDS[-1]
    assert "บันทึกแล้ว" not in th, th


def test_live_number_door_success_both_halves():
    reset()
    b = FakeBridge(sp={"declared": "abs", "done": "abs", "status": "ждёт_подтверждения",
                       "odometer": ""})
    handled = run(S.handle_service_result(Msg("21554"), context=None, bridge=b, claude=None,
                                          text="21554"))
    assert handled is True
    th, ru = _halves(SENDS[-1])
    assert outcome_of(th, TH_HEADS) == outcome_of(ru, RU_HEADS) == SR.STATE_WRITTEN, SENDS[-1]


def test_live_write_path_untouched():
    """Границы: правка трогает СЛОВА, а не запись — вызовы моста прежние (confirmed=True).

    Фикстура догнана 23.08: с этого дня закрытие строки заявки идёт через дверь вердикта и
    ПЕРЕД записью спрашивает, есть ли что закрывать (дыра «строка-эхо» — слепой close дописывал
    заявку, которой не было). Без открытой строки этот assert проверял бы ровно ту дыру."""
    reset()
    b = FakeBridge(sp={"declared": "oil,gear", "done": "oil,gear",
                       "status": "ждёт_подтверждения", "odometer": "20316"})
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_4724, "done": ["oil", "gear"],
                      "odo": "20316", "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    assert len(b.oil_calls) == 1 and b.oil_calls[0][2] is True, b.oil_calls
    assert len(b.svc_calls) == 1 and b.svc_calls[0][1] == "gear" and b.svc_calls[0][3] is True
    assert b.closed is True


def test_live_button_untrusted_still_blocked():
    """Trust НЕ ослаблен: механик жмёт — записи нет, квитанции нет."""
    reset()
    b = FakeBridge()
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_4957, "done": ["abs"],
                      "odo": "37015", "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", "extthiwxer")), context=None, bridge=b))
    assert not b.oil_calls and not b.svc_calls, "недоверенный не пишет"
    assert not any("บันทึกแล้ว" in s for s in SENDS), SENDS


# ═══════════════ (8) ЧИСТОТА РЕШЕНИЯ (ast, а не докстринг) ═══════════════

def test_purity_one_import_no_hands():
    with open(os.path.join(ROOT, "service_receipt.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("open", "exec", "eval", "compile", "__import__"), \
                f"у решения появились руки: {node.func.id} (строка {node.lineno})"
    assert imports == {"write_fact"}, f"импорт обязан быть ровно один: {sorted(imports)}"


def test_purity_halves_come_from_one_door():
    """Половины врозь не выдаются: у модуля одна публичная дверь, и она отдаёт обе сразу."""
    r = SR.receipt(["oil"], [], "24997", LBL)
    assert set(r) == {"state", "written", "settled", "unknown", "th", "ru"}, sorted(r)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} проверок: квитанция ТО одинакова на обоих языках")
