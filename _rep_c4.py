import sys, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient
br = BridgeClient()
def call(fn, tries=8):
    for i in range(tries):
        try:
            r = fn()
            if isinstance(r, dict) and r.get("error") in ("timeout","exhausted"):
                time.sleep(2); continue
            return r
        except Exception as e:
            print("err", e); time.sleep(2)
    return {"ok": False}
REPORT = """DONE 2026-06-30 (карточка: ВСЕ 4 обязательных ТО + читабельный рендер, commit 5a7f832, НЕ деплоено):
ГИТ (шаг 0, read-only): ahead=0, origin==local (cca682b) — синхронно; ручных непушенных коммитов НЕТ.
ЗАДАЧА1 — все 4 регламентных вида ВСЕГДА (масло/редуктор/ABS/возд.фильтр): источник последней замены = Лист1
cols I/J/K/L (find_bike oil_last_km/gear_last_km/abs_last_km/airfilter_last_km), НЕ service_list (Bot Data — он
неполный, прятал виды без записи → отсюда «невидимые» просрочки). Статусы: ✅ ещё N км · ⚠️ просрочено на N /
пора сейчас · ❗ НЕ ДЕЛАЛОСЬ (нет записи) — явно, не молчим. gear только скутер (_bike_class по имени; мото →
interval None → вид скрыт). «масляный фильтр» из ТЗ = airfilter (воздушный, col L, 20000) — системный
column-kind (_SP_COL_KINDS); отдельного oil-фильтра на NMAX/индийских НЕТ (предметная модель 28.06).
КРИТИЧНО — ТЕКУЩИЙ ПРОБЕГ: теперь = max(Лист1 col H find_bike.mileage [ЖИВОЙ пробег, НЕ покупочный вопреки
старой подписи — услуги ниже него невозможны], последние current_km из service_list). Раньше брался устаревший
фото-замер из service_list → просрочки прятались. 4255: было «пробег 24302» (старое фото 28.06) → стало 29275.
ЗАДАЧА2 — рендер: разделители ─── (аренда / Плановое ТО / текущий ремонт / История), эмодзи 🛢⚙️🛡💨 + статусы
✅⚠️❗, аренда сверху, история компактной строкой «📜 На пробеге: …». _bilingual сохранён, 🇹🇭 без кириллицы.
ДО (4255 🇷🇺): «пробег 24302 · ТО Oil: в норме, следующее 28094 км (ещё 3792 км)» — ТОЛЬКО oil; gear/abs/
airfilter СКРЫТЫ (нет записи в Bot Data).
ПОСЛЕ (4255 🇷🇺): «пробег 29275 · ─Плановое ТО─ · 🛢 Масло: ⚠️ просрочено на 1181 км · ⚙️ Редуктор: ⚠️ просрочено
на 8275 км · 🛡 ABS oil: ✅ ещё 10025 км · 💨 Возд.фильтр: ❗ не делалось». Скрытые просрочки ВСКРЫЛИСЬ.
ТЕСТ: test_card_remaining переписан (4 вида / не делалось / просрочено / граница 0 / скутер-vs-мото / TH чистый);
test_card/test_fmt/test_z3 под новый формат. py_compile OK. Гейт 24✅; info/uxd/servicing/works/bilingual/ТО30
регресс PASS. Бэкап=коммит 5a7f832 (без push) + .bak-card4to. Зона 🟢 (чтение Лист1/service_list + расчёт +
рендер, без записи). Откат=git revert 5a7f832 + restart.
ФЛАГ владельцу: (1) «масляный фильтр» в карточке = airfilter (ВОЗДУШНЫЙ); если имелся в виду ОТДЕЛЬНЫЙ масляный
фильтр — его нет ни в Лист1, ни в модели (нужен новый столбец+Bridge = красное), уточнить. (2) Пробег в карточке
теперь живой (29275), а не фото-замер (24302) — это и вскрывает просрочки; если живой пробег где-то завышен в
Лист1 col H — просрочка будет завышена, проверяемо по строке.
ЖДУ «да»: 🟠 restart → ретест карточки (кнопка «Инфо» → 4 вида ТО со статусами).
АВТО-ПОДРЕЗКА: канон только 30.06 → переносить нечего."""
PULSE = ("2026-06-30 | 🟢 | Карточка: 4 обязательных ТО ВСЕГДА (масло/редуктор/ABS/фильтр, ❗не делалось где нет "
         "записи) + читабельный рендер (секции ───/эмодзи) СОБРАНЫ (5a7f832). КРИТ: пробег теперь max(Лист1 colH, "
         "service_list) → просрочки вскрылись (4255 oil+gear). git синхр, гейт 24✅. НЕ деплоено | жду: «да» на "
         "restart; уточнить «масляный фильтр»=воздушный? | детали→cc_log «карточка 4 ТО 30.06»")
text = call(lambda: br._call("read_doc", name="cc_log")).get("text","")
if "📦 cc_log" not in text:
    print("канон битый — аборт"); sys.exit(1)
lines = text.split("\n")
hidx = next(i for i,ln in enumerate(lines) if ln.strip() and set(ln.strip())=={"═"})
new = "\n".join(lines[:hidx+1]) + "\n\n" + REPORT + "\n\n" + "\n".join(lines[hidx+1:]).lstrip("\n")
ok=False
for a in range(6):
    call(lambda: br.write_doc(text=new, name="cc_log"))
    t = call(lambda: br._call("read_doc", name="cc_log")).get("text","")
    ok = "ВСЕ 4 обязательных ТО + читабельный рендер, commit 5a7f832" in t and "просрочено на 8275" in t
    print(f"  канон {a+1}: len={len(t)} → {'OK' if ok else '...'}")
    if ok: break
    time.sleep(3)
if not ok:
    print("канон не подтверждён"); sys.exit(1)
for a in range(6):
    call(lambda: br.write_doc(text=PULSE, name="pulse"))
    if "4 обязательных ТО ВСЕГДА" in call(lambda: br._call("read_doc", name="pulse")).get("text",""):
        print("ПУЛЬС OK"); break
    time.sleep(3)
print("=== ОТЧЁТ ЗАПИСАН ===")
