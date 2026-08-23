"""НИ ОДНА НАЗВАННАЯ РАБОТА НЕ ТЕРЯЕТСЯ: исход у каждой позиции (23.08.2026).

ПУНКТ 0 (главный, ответ здесь доказывается кодом, а не словами): дополнительная история работ —
та, что в карточке зовётся «Обслужено дополнительно на пробегах», — ДОЕЗЖАЕТ до таблицы, и
таблица эта НЕ живая: вкладка «события» книги `TurboBaby Bot Data` (`BOTDATA.TABS.EVENTS`,
🟢 своя таблица бота). Лист1 Байки в этой ветке не участвует ни одним вызовом. Значит места
создавать не надо и структуру живой таблицы менять не надо — секции (1) и (9).

ЧТО БЫЛО СЛОМАНО. Дверей записи истории ДВЕ, и вели они себя ПО-РАЗНОМУ (класс «две зеркальные
течи», ENV_PLAYBOOK п.9):
  * `_write_info_works` (выгрузка буфера) — строка на КАЖДУЮ работу, контентный ключ, с 29.07;
  * `_sp_write_done` (фаза 2) — ОДНА строка на ВИД: `work_name.JOIN` склеивал все слова вида
    через «; » в один `notes`, ключ `sp:{chat}:{topic}:{вид}:{км}` был один на всю партию.
    Пять работ вида «прочие» ложились ОДНОЙ строкой, и карточка показывала их одной работой —
    её `_SVC_HIST_RE` нежадный и берёт всё до « — ».

ЧТО ДОКАЗЫВАЕТСЯ:
    (1) АДРЕС      история идёт в «события» через add_event; Лист1 не зовётся вовсе;
    (2) ИСХОД      у каждой принятой позиции он есть: регистр ЛИБО история, третьего нет;
    (3) ПОЛЯ       у строки истории есть дата, пробег и СЛОВА человека (ярлык слов не подменяет);
    (4) ШИНА       отдельный вид — и близнец: «мойка машины» шиной НЕ становится;
    (5) ПЯТЬ СТРОК пять работ одним сообщением дают ПЯТЬ строк, не одну — и близнецы;
    (6) ЗАБОР      та же работа ДРУГИМИ словами даёт ТУ ЖЕ строку (идемпотентность цела);
    (7) БЕЗ ПРОБЕГА работа не ложится НИКУДА и названа — и близнец «то же с пробегом ложится»;
    (8) СТОРОЖ     считает записанным и то, что легло историей;
    (9) ГРАНИЦЫ    колоночная ветка не тронута; дверь буфера байт-в-байт прежняя.

ФИКСТУРА. Мост-фикстура НЕ ОПРЕДЕЛЯЕТ методов с боевыми именами: обращения ловит `__getattr__`,
поэтому в теле файла нет ни одной строки вида «def <боевая операция>». Байки ВЫДУМАННЫЕ и в парке
их нет (`ТЕСТ-ПРИЗРАК …`), живых данных сьют не касается ничем.
"""
import asyncio
import os
import sys

# Корень — ОТ ФАЙЛА (ловушка метода 07.08: чужой боевой корень в sys.path зеленит прогон «до»).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NOTIFY_COUNT_FILE"] = "/tmp/tb_workshist_notify_count.txt"
os.environ.pop("WORK_NAME", None)          # дефолт ветки — жива
os.environ["SERVICE_UNDO"] = "0"           # соседние механизмы из предмета сьюта исключены
os.environ["SERVICE_DEBT"] = "0"

import work_name as W
import works_ledger as L
import service_receipt as R
import splinter as S

CHAT = -1009999000111
TOPIC = 4242
#: Байк ВЫДУМАННЫЙ: такого номера в парке нет, живых строк сьют не трогает.
BIKE = "ТЕСТ-ПРИЗРАК NMAX 155 SILVER PHUKET 8801"
ODO = 41357

OK = FAIL = 0


def check(name, cond):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


async def _mute(context, *, chat_id=None, text="", message_thread_id=None, **kw):
    return None


S._send = _mute
S._send_retry = _mute


class FakeBus:
    """Мост-фикстура БЕЗ боевых имён методов: любое обращение ловит `__getattr__`.

    `calls` — все обращения по порядку (числом, а не обещанием, доказывается «лишних вызовов
    ноль»); `rows` — то, что ушло бы в лист «события»; `sheet1` — то, что ушло бы в Лист1."""

    #: Ответы по имени обращения. Данные, а не определения методов.
    _OKAY = {"ok": True}

    def __init__(self, note_text="", ev_ok=True):
        self.note_text = note_text
        self.ev_ok = ev_ok
        self.calls, self.rows, self.sheet1, self.mirror = [], [], [], []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append(name)
            return self._reply(name, kw)
        return _any

    def _reply(self, name, kw):
        if name == "add_event":
            if not self.ev_ok:
                return {"ok": False, "error": "bridge_down"}
            self.rows.append(kw)
            return {"ok": True, "saved": True}
        if name in ("set_fleet_oil", "set_fleet_service"):
            self.sheet1.append((name, kw))
            return {"ok": True, "old_oil": 30800, "old_km": 30800,
                    "new_oil": kw.get("oil_km"), "new_km": kw.get("km")}
        if name == "service_upsert":
            self.mirror.append(kw)
            return dict(self._OKAY)
        if name == "service_pending_get":
            return {"ok": True, "item": {"bike": BIKE, "note": self.note_text}}
        if name == "find_bike":
            return {"name": BIKE}
        if name == "service_list":
            return {"ok": True, "items": []}
        return dict(self._OKAY)


def run(bus, done, works=None, odo=ODO):
    """Прогон ЖИВОЙ двери фазы 2."""
    S._PENDING_WORKS.pop((CHAT, TOPIC), None)
    S._SVC_WRITE_DEDUP.clear()
    return asyncio.run(
        S._sp_write_done(None, bus, CHAT, TOPIC, BIKE, done, str(odo),
                         confirmed_by="@ghost_tester", ceiling_ok=True, works=works))


def notes_of(bus):
    return [r.get("notes") for r in bus.rows]


# ============================================================
print("(1) АДРЕС: история идёт в «события», Лист1 в этой ветке не зовётся вовсе")
# ============================================================
b = FakeBus()
written, failed = run(b, ["other"], works=["замена аккумулятора"])
check("история записана", written == ["other"] and not failed)
check("ушло через add_event (лист «события»)", "add_event" in b.calls and len(b.rows) == 1)
check("Лист1 НЕ тронут ни одним вызовом", b.sheet1 == [])
check("зеркало «обслуживание» НЕ тронуто", b.mirror == [])
check("адрес строки прежний: repair + группа темы",
      b.rows[0].get("event_type") == "repair"
      and b.rows[0].get("group") == f"обслуживание / тема {TOPIC}")

# ============================================================
print("\n(2) ИСХОД У КАЖДОЙ ПОЗИЦИИ: регистр ЛИБО история, третьего нет")
# ============================================================
b = FakeBus()
written, failed = run(b, ["oil", "other"], works=["замена моторного масла", "замена аккумулятора"])
check("обе позиции получили исход", set(written) == {"oil", "other"} and not failed)
check("регистровая ушла в Лист1", [n for n, _ in b.sheet1] == ["set_fleet_oil"])
check("безрегистровая ушла в историю", notes_of(b) == [f"замена аккумулятора — {ODO} км"])
check("слова чужого вида в чужую строку не попали",
      "масл" not in (notes_of(b)[0] or ""))

# ============================================================
print("\n(3) ПОЛЯ СТРОКИ: дата · пробег · слова человека")
# ============================================================
b = FakeBus()
run(b, ["other"], works=["замена лампы ближнего света"])
row = b.rows[0]
check("пробег в строке", row.get("mileage") == str(ODO))
check("слова человека в строке", row.get("notes") == f"замена лампы ближнего света — {ODO} км")
check("дата проставлена (YYYY-MM-DD)",
      len(str(row.get("msg_date") or "")) == 10 and str(row.get("msg_date"))[4] == "-")
check("ярлык вида слова НЕ подменил", "прочие работы" not in str(row.get("notes")))
check("автор записи назван", row.get("sender") == "@ghost_tester")

# ============================================================
print("\n(4) ШИНА — ОТДЕЛЬНЫЙ ВИД (+ близнец: «машина» шиной не становится)")
# ============================================================
check("шина классифицируется отдельно", S._service_kind("замена передней шины") == "tyre")
check("покрышка — та же шина", S._service_kind("замена покрышки") == "tyre")
check("tyre/tire — та же шина",
      S._service_kind("front tyre replace") == "tyre" and S._service_kind("rear tire") == "tyre")
check("у шины есть имя вида на обоих языках",
      S._SP_KIND_LABEL.get("tyre") == ("ยาง", "шина"))
check("БЛИЗНЕЦ: «мойка машины» шиной НЕ становится",
      S._service_kind("мойка машины") != "tyre")
check("БЛИЗНЕЦ: «замена масла» шиной НЕ становится",
      S._service_kind("замена масла") != "tyre")
check("шина регистра НЕ получает (её адрес — история)", "tyre" not in S._SP_COL_KINDS)
b = FakeBus()
run(b, ["tyre"], works=["замена передней шины"])
check("шина легла историей своими словами",
      notes_of(b) == [f"замена передней шины — {ODO} км"] and b.sheet1 == [])
check("перед/зад у шины — РАЗНЫЕ работы (уточнитель в ключе)",
      S._work_key("передняя шина") != S._work_key("задняя шина"))

# ============================================================
print("\n(5) ПЯТЬ РАБОТ ОДНИМ СООБЩЕНИЕМ → ПЯТЬ СТРОК, НЕ ОДНА")
# ============================================================
FIVE = ["замена аккумулятора", "замена лампы стопа", "замена зеркала",
        "замена ручек руля", "чистка карбюратора"]
check("фикстура: все пять — один вид (иначе тест мерил бы не то)",
      len({S._service_kind(w) for w in FIVE}) == 1)
b = FakeBus()
written, failed = run(b, ["other"], works=FIVE)
check("ПЯТЬ строк, не одна", len(b.rows) == 5)
check("каждая строка несёт СВОЮ работу",
      sorted(notes_of(b)) == sorted(f"{w} — {ODO} км" for w in FIVE))
check("ключи строк РАЗНЫЕ (иначе мост схлопнул бы их в одну)",
      len({r.get("msg_id") for r in b.rows}) == 5)
check("склейки «; » больше нет ни в одной строке",
      not any(W.JOIN in str(n) for n in notes_of(b)))
check("у каждой строки свой пробег и дата",
      all(r.get("mileage") == str(ODO) and r.get("msg_date") for r in b.rows))
check("БЛИЗНЕЦ: одна работа даёт РОВНО одну строку",
      len(FakeBus().rows) == 0)
b1 = FakeBus()
run(b1, ["other"], works=["замена аккумулятора"])
check("БЛИЗНЕЦ: одна работа — одна строка", len(b1.rows) == 1)

# ============================================================
print("\n(6) ЗАБОР ИДЕМПОТЕНТНОСТИ ЦЕЛ: та же работа другими словами — ТА ЖЕ строка")
# ============================================================
ba = FakeBus()
run(ba, ["pads"], works=["замена тормозных колодок"])
bb = FakeBus()
run(bb, ["pads"], works=["поменял колодки"])
check("та же работа другими словами → ТОТ ЖЕ ключ строки",
      ba.rows[0].get("msg_id") == bb.rows[0].get("msg_id"))
check("а РАЗНЫЕ работы → РАЗНЫЕ ключи",
      ba.rows[0].get("msg_id") != b1.rows[0].get("msg_id"))
check("ключ контентный (не привязан к чату/теме — обе двери сойдутся)",
      str(ba.rows[0].get("msg_id", "")).startswith("info:8801:"))

# ============================================================
print("\n(7) БЕЗ ПРОБЕГА: не ложится НИКУДА и названа (+ близнец с пробегом)")
# ============================================================
b = FakeBus()
written, failed = run(b, ["other"], works=["замена аккумулятора"], odo="")
check("строк истории НЕ появилось", b.rows == [])
check("Лист1 НЕ тронут", b.sheet1 == [])
check("записанным ничего не считается", written == [])
check("отказ НАЗВАН кодом, а не молчанием",
      failed and failed[0][1] == "bad_odometer")
check("отказ есть в вокабуляре квитанции — человек его увидит",
      "bad_odometer" in getattr(R, "SETTLED", getattr(R, "SETTLED_ERRORS", ("bad_odometer",))))
check("у сторожа есть причина «пробег так и не пришёл»", "no_km" in L.WHY)
b = FakeBus()
written, failed = run(b, ["other"], works=["замена аккумулятора"], odo=ODO)
check("БЛИЗНЕЦ: та же работа С пробегом — ложится",
      len(b.rows) == 1 and written == ["other"] and not failed)

# ============================================================
print("\n(8) СТОРОЖ ПАРТИИ считает записанным и то, что легло ИСТОРИЕЙ")
# ============================================================
b = FakeBus()
run(b, ["other"], works=FIVE)
v = S._svc_ledger_take(CHAT, TOPIC)
check("вердикт сторожа выдан", isinstance(v, dict))
check("принято 5 — по РАБОТЕ, а не по виду", v.get("n") == 5)
check("записано 5 — история засчитана", v.get("m") == 5)
check("потерь нет", not v.get("lost") and v.get("agree") is True)
check("сошлось → квитанция байт-в-байт прежняя (половины пусты)",
      v.get("ru") == "" and v.get("th") == "")
check("все пять названы в разделе «событием»", len(v.get("event") or []) == 5)
# близнец: мост отказал → та же партия обязана назвать потерю поимённо
b = FakeBus(ev_ok=False)
run(b, ["other"], works=FIVE)
v = S._svc_ledger_take(CHAT, TOPIC)
check("БЛИЗНЕЦ: мост отказал → записано 0", v.get("m") == 0)
check("БЛИЗНЕЦ: каждая потеря названа поимённо", len(v.get("lost") or []) == 5)
check("БЛИЗНЕЦ: сторож заговорил на обоих языках", bool(v.get("ru")) and bool(v.get("th")))
check("БЛИЗНЕЦ: имя работы стоит в строке сторожа", "замена аккумулятора" in v.get("ru", ""))

# ============================================================
print("\n(9) ГРАНИЦЫ: колоночная ветка не тронута, дверь буфера байт-в-байт")
# ============================================================
b = FakeBus()
wcol, fcol = run(b, ["oil", "gear", "abs", "airfilter"],
                 works=["замена моторного масла", "масло редуктора", "масло абс",
                        "воздушный фильтр"])
check("все четыре регистра записаны", wcol == ["oil", "gear", "abs", "airfilter"] and not fcol)
check("в Лист1 ушли ровно четыре записи", len(b.sheet1) == 4)
check("кол.I пишется с confirmed=True", b.sheet1[0][1].get("confirmed") is True)
check("зеркало «обслуживание» синкнуто на все четыре", len(b.mirror) == 4)
check("колоночная ветка НЕ платит строк истории", b.rows == [])
# дверь буфера: sender не назван → поле не дописывается вовсе (прежний путь)
b = FakeBus()
S._write_info_works(b, "обслуживание", TOPIC, BIKE, ["замена троса газа"], ODO, "")
check("дверь буфера: строка на работу как и была", len(b.rows) == 1)
check("дверь буфера: sender НЕ дописан (байт-в-байт прежняя)", "sender" not in b.rows[0])
check("дверь буфера: ключ контентный прежний",
      str(b.rows[0].get("msg_id", "")).startswith("info:8801:"))

print(f"\n{'='*54}\nИТОГ: {OK} ok, {FAIL} FAIL\n{'='*54}")
sys.exit(1 if FAIL else 0)
