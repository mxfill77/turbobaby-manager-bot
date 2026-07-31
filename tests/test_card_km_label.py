"""Метка пробега в истории работ карточки Инфо: «на текущем пробеге» = ФАКТ, а не заглушка.

КЛАСС (инцидент 31.07.2026, карточка NMAX 155CC GREEN-B PHUKET 4957, 18:03 BKK, код 1c23895):
шапка «пробег 37000 км» и строка истории «38982 км (на текущем пробеге)» в ОДНОЙ карточке.
38982 ≠ 37000 — метка врала. Источник у метки и шапки БЫЛ ОДИН И ТОТ ЖЕ (`cur_km` = _odo_current,
splinter.py: шапка — `_block`, метка — `_km_ago(cur_km, ...)`); врал не источник, а ветка `d <= 0`
в `_km_ago`: работу ВЫШЕ текущего пробега она «мягко деградировала» в «на текущем пробеге».
Так невыразимое расхождение превращалось в ложное утверждение о факте.

КОНТРАКТ ПОСЛЕ ФИКСА (одно правило на ОБЕ языковые ветки — внутри `_km_ago`, не двумя копиями):
  d == 0  → «на текущем пробеге» / «ไมล์ปัจจุบัน»   (правда: км работы РАВЕН текущему)
  d >  0  → «N км назад» / «N กม.ที่แล้ว»
  d <  0  → метки НЕТ ВОВСЕ (пустая строка; скобки в рендере не печатаются)
  нечисло → «на пробеге» / «บนไมล์»                (нейтральная заглушка, факта не утверждает)

ЖИВОЙ ФОРМАТ фикстуры снят read-only разведкой прода 31.07.2026 (find_bike / service_list /
read_events по 4957) — не идеализирован (класс «моки = живой формат листа», CLAUDE.md):
  • service_list.current_km — ЧИСЛО (37000), updated_at — ISO-Z «2026-07-31T07:31:12.732Z»;
  • read_events.mileage — СТРОКА («38982»), notes — «замена передних тормозных колодок — 38982 км»;
  • find_bike.mileage = 12600 — это пробег ПРИ ПОКУПКЕ (кол.H), в текущем не участвует.
Строку 38982 в живой таблице НЕ трогаем — она чинится отдельно; карточка обязана быть честной
и при ней (сегодняшнее состояние прода воспроизведено дословно).
"""
import os, sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # ручной прогон вне гейта тоже не шлёт пушей в личку
import splinter as S

CHAT = -1002751134848
TOPIC = 79            # живая тема байка 4957

res = []


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    res.append(bool(c))
    return c


# ── живой снимок прода 31.07.2026 (read-only разведка), 4957 ──────────────────────────────
FB_4957 = {"number": 2, "status": "ДОМА", "name": "NMAX 155CC GREEN-B PHUKET 4957",
           "purchase_date": "2022-09-05 00:00", "year": 2020, "cost": 73000,
           "total_revenue": 151163, "mileage": 12600,          # кол.H — ПРИ ПОКУПКЕ, не текущий
           "oil_last_km": 37000, "gear_last_km": 36982, "abs_last_km": 12600,
           "airfilter_last_km": 0, "current_rental": None}
SL_4957 = [
    {"updated_at": "2026-07-31T07:31:12.732Z", "bike": "NMAX 155CC GREEN-B PHUKET 4957",
     "topic_id": 79, "service_type": "oil", "current_km": 37000, "last_service_km": 30800,
     "interval_km": 4000, "next_km": 34800, "status": "overdue", "pinned_msg_id": "",
     "last_reminded_at": 17853161900047500, "note": ""},
    {"updated_at": "2026-07-31T07:31:23.001Z", "bike": "NMAX 155CC GREEN-B PHUKET 4957",
     "topic_id": 79, "service_type": "gear", "current_km": 37000, "last_service_km": 36982,
     "interval_km": 4000, "next_km": 40982, "status": "ok", "pinned_msg_id": "",
     "last_reminded_at": "", "note": ""},
]
EV_4957 = [
    {"recorded_at": "2026-07-31T07:36:31.864Z", "msg_date": "Fri Jul 31 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
     "event_type": "other", "mileage": "",
     "notes": "обнаружена неисправность, напоминание делать фото резины при инспекции, заказ покрышек: 6 задних ND (xmax300, nmax155) + 2 передних"},
    {"recorded_at": "2026-07-31T07:31:06.809Z", "msg_date": "Fri Jul 31 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
     "event_type": "other", "mileage": "37000", "notes": "текущий пробег 37000"},
    {"recorded_at": "2026-07-29T09:32:19.528Z", "msg_date": "Wed Jul 29 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
     "event_type": "photo", "mileage": "",
     "notes": "Приборная панель Yamaha, общий пробег 38982 км, индикатор топлива показывает полный бак, время 4:16, экран с пылью и разводами | грязный"},
    {"recorded_at": "2026-07-29T09:32:15.576Z", "msg_date": "Wed Jul 29 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
     "event_type": "repair", "mileage": "38982", "notes": "замена передних тормозных колодок — 38982 км"},
    {"recorded_at": "2026-07-29T09:24:34.536Z", "msg_date": "Wed Jul 29 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
     "event_type": "photo", "mileage": "",
     "notes": "На фото изношенные тормозные колодки байка, лежат рядом с колесом. Колодки сильно стёрты, требуют замены. | Использованные тормозные колодки байка, сильно изношены, "},
]


class BR:
    """Мок Bridge на живом снимке. Ничего не пишет (карточка read-only по контракту)."""

    def __init__(self, fb=None, sl=None, ev=None):
        self._fb = FB_4957 if fb is None else fb
        self._sl = SL_4957 if sl is None else sl
        self._ev = EV_4957 if ev is None else ev

    def _call(self, a, **k):
        return {"ok": False}                     # книга интервалов недоступна → хардкод-фоллбэк

    def find_bike(self, b):
        return dict(self._fb)

    def service_list(self):
        return {"items": [dict(r) for r in self._sl]}

    def read_events(self, bike, limit=8):
        return {"ok": True, "bike": bike, "items": [dict(e) for e in self._ev]}

    def service_pending_get(self, c, t, b):
        return {"ok": False}

    def service_pending_list(self, status=None):
        return {"ok": True, "items": []}


def card(**kw):
    return S._build_bike_card(BR(**kw), CHAT, TOPIC, "4957")


# ── 1) ГЛАВНЫЙ РЕГРЕСС: живая карточка 4957 как она есть сегодня ──────────────────────────
print("(1) живая карточка 4957: шапка 37000, в истории строка 38982")
m = card()
ok("<b>пробег 37000 км</b>" in m, "RU-шапка = 37000 (единый источник _odo_current)")
ok("<b>ไมล์ 37000 กม.</b>" in m, "TH-шапка = 37000 (тот же источник)")
ok("38982 км" in m and "замена передних тормозных колодок" in m,
   "строка работы 38982 ПОКАЗАНА (её не прячем — прячем только ложную метку)")
ok("38982 км (на текущем пробеге)" not in m, "RU: метки «на текущем пробеге» у 38982 НЕТ (38982 ≠ 37000)")
ok("38982 กม. (ไมล์ปัจจุบัน)" not in m, "TH: метки «ไมล์ปัจจุบัน» у 38982 НЕТ (та же ветка, не копия)")
ok("на текущем пробеге" not in m, "RU: ложной метки нет НИГДЕ в карточке")
ok("ไมล์ปัจจุบัน" not in m, "TH: ложной метки нет НИГДЕ в карточке")
ok("()" not in m, "пустых скобок «()» в карточке нет (метки нет → скобок нет вовсе)")

# ── 2) НЕ ПЕРЕСОЛИТЬ: работа РОВНО на текущем пробеге метку сохраняет ─────────────────────
print("(2) работа ровно на текущем пробеге (37000 = 37000) — метка ПРАВДИВА, остаётся")
EV_EQ = [{"recorded_at": "2026-07-31T07:00:00.000Z", "msg_date": "Fri Jul 31 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
          "event_type": "repair", "mileage": "37000", "notes": "регулировка цепи — 37000 км"}]
m2 = card(ev=EV_EQ)
ok("37000 км (на текущем пробеге)" in m2, "RU: d == 0 → метка есть")
ok("37000 กม. (ไมล์ปัจจุบัน)" in m2, "TH: d == 0 → метка есть")

# ── 3) работа НИЖЕ текущего — обычное «N км назад» ────────────────────────────────────────
print("(3) работа ниже текущего (37000 − 36000 = 1000)")
EV_LT = [{"recorded_at": "2026-07-20T07:00:00.000Z", "msg_date": "Mon Jul 20 2026 00:00:00 GMT+0700 (Indochina-Zeit)",
          "event_type": "repair", "mileage": "36000", "notes": "замена свечи — 36000 км"}]
m3 = card(ev=EV_LT)
ok("36000 км (1000 км назад)" in m3, "RU: 1000 км назад")
ok("36000 กม. (1000 กม.ที่แล้ว)" in m3, "TH: 1000 กม.ที่แล้ว")

# ── 4) одометра нет вовсе → нейтральная заглушка, а не утверждение о факте ────────────────
print("(4) текущий пробег неизвестен (нет своего одометра и нет *_last_km)")
FB_NOODO = {"name": "NMAX 155CC GREEN-B PHUKET 4957", "status": "ДОМА", "mileage": 12600,
            "oil_last_km": 0, "gear_last_km": 0, "abs_last_km": 0, "airfilter_last_km": 0}
m4 = card(fb=FB_NOODO, sl=[], ev=EV_LT)
ok("36000 км (на пробеге)" in m4, "RU: нечисловой cur → нейтральное «на пробеге» (факта не утверждает)")
ok("36000 กม. (บนไมล์)" in m4, "TH: нечисловой cur → «บนไมล์»")
ok("на текущем пробеге" not in m4 and "ไมล์ปัจจุบัน" not in m4,
   "неизвестный пробег НЕ выдаётся за «текущий»")

# ── 5) единица правила: _km_ago — таблица ветвей × два языка (одна функция, не две копии) ─
print("(5) _km_ago: одно правило закрывает обе языковые ветки")
TABLE = [
    # (cur,      km,      ru,                    th)
    ("37000", "38982", "",                    ""),                  # выше текущего → метки нет
    ("37000", "37000", "на текущем пробеге",  "ไมล์ปัจจุบัน"),
    ("37000", "36000", "1000 км назад",       "1000 กม.ที่แล้ว"),
    ("",      "36000", "на пробеге",          "บนไมล์"),
    ("37000", "",      "на пробеге",          "บนไมล์"),
    ("37 000", "36 000", "1000 км назад",     "1000 กม.ที่แล้ว"),   # живой формат: пробел-разделитель
]
for cur, km, exp_ru, exp_th in TABLE:
    got_ru = S._km_ago(cur, km, False)
    got_th = S._km_ago(cur, km, True)
    ok(got_ru == exp_ru, f"_km_ago({cur!r},{km!r},ru) = {got_ru!r} (ждём {exp_ru!r})")
    ok(got_th == exp_th, f"_km_ago({cur!r},{km!r},th) = {got_th!r} (ждём {exp_th!r})")

# симметрия языков: пусто — значит пусто в ОБЕИХ ветках (иначе «через неделю вылезет тайская»)
ok(bool(S._km_ago("37000", "38982", False)) == bool(S._km_ago("37000", "38982", True)),
   "RU и TH молчат/говорят СИНХРОННО (правило одно, копий нет)")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
