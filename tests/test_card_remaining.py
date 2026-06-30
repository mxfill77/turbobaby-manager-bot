"""Карточка: ПЛАНОВОЕ ТО — 4 обязательных вида ВСЕГДА (масло/редуктор/ABS/возд.фильтр), статусы
✅ ещё / ⚠️ просрочено / ⚠️ пора сейчас / ❗ не делалось; gear только скутер; СТИЛЬ: <b>жирный</b> на важном,
эмодзи минимум, тонкие ───── разделители, parse_mode=HTML."""
import os, sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# (1) _mand_line — статусы + HTML-жирный на важном (граничные включительно)
print("(1) _mand_line (HTML):")
res.append(ok(S._mand_line("oil", 24094, 4000, "27000")[1] == "   Масло — ✅ ещё <b>1094</b> км (срок 28094)", ">0 → ✅ ещё <b>N</b> км"))
res.append(ok(S._mand_line("oil", 24094, 4000, "29275")[1] == "   Масло — ⚠️ <b>просрочено на 1181 км</b>", "<0 → ⚠️ <b>просрочено на N</b>"))
res.append(ok(S._mand_line("oil", 24094, 4000, "28094")[1] == "   Масло — ⚠️ <b>пора сейчас</b> (срок 28094)", "==0 → ⚠️ <b>пора сейчас</b> (граница)"))
res.append(ok(S._mand_line("abs", 0, 10000, "29275")[1] == "   ABS — ❗ <b>не делалось</b>", "last 0 → ❗ <b>не делалось</b>"))
res.append(ok(S._mand_line("airfilter", None, 20000, "29275")[1] == "   Возд. фильтр — ❗ <b>не делалось</b>", "last None → ❗ не делалось"))
res.append(ok(S._mand_line("gear", 17000, None, "29275") is None, "gear interval None (мото) → None (скрыт)"))
res.append(ok(S._mand_line("oil", 24094, 4000, "")[1] == "   Масло — замена 24094 · срок 28094 км", "нет текущего пробега → срок без остатка"))

# (2) скутер vs мото + интервал воздушного фильтра 20000
print("(2) скутер/мото + интервал воздушного:")
fb = S._SVC_INTERVALS_FALLBACK
res.append(ok(S._bike_class("NMAX 155 4255", fb) == "scooter" and S._bike_class("NINJA 400 6334", fb) == "moto", "NMAX=скутер, NINJA=мото"))
res.append(ok(fb["gear"]["scooter"] == 4000 and fb["gear"]["moto"] is None, "gear: скутер 4000, мото — не применимо"))
res.append(ok(fb["airfilter"] == 20000 and fb["abs"] == 10000, "воздушный фильтр 20000, ABS 10000 (зашиты в фоллбэк)"))

# (3) карточка: все 4 вида + статусы + стиль (RU)
mand = [
    {"kind": "oil", "last": 24094, "interval": 4000},        # 28094-29275 = просрочено 1181
    {"kind": "gear", "last": 17000, "interval": 4000},       # 21000-29275 = просрочено 8275 (скутер)
    {"kind": "abs", "last": 29300, "interval": 10000},       # 39300-29275 = ещё 10025
    {"kind": "airfilter", "last": 0, "interval": 20000},     # нет записи → не делалось
]
m = S.msg_bike_card("NMAX 155 4255", "29275", mand,
                    {"state": "В аренде", "client": "Gamza", "expired": True, "end": "17.06.2026"})
print("\n(3) карточка — 4 вида + стиль (RU):")
res.append(ok("🐀 <b>NMAX 155 4255</b>" in m and "пробег <b>29275</b> км" in m, "имя байка и пробег — <b>жирные</b>"))
res.append(ok("Масло — ⚠️ <b>просрочено на 1181 км</b>" in m, "масло просрочено (жирным)"))
res.append(ok("Редуктор — ⚠️ <b>просрочено на 8275 км</b>" in m, "редуктор просрочен (скрытая просрочка видна)"))
res.append(ok("ABS — ✅ ещё <b>10025</b> км (срок 39300)" in m, "ABS ещё 10025"))
res.append(ok("Возд. фильтр — ❗ <b>не делалось</b>" in m, "фильтр без записи → ❗ не делалось"))
res.append(ok("───── Плановое ТО ─────" in m, "тонкий разделитель «Плановое ТО»"))
res.append(ok("⚠️ <b>аренда истекла 17.06.2026</b>" in m, "аренда истекла — ⚠️ жирным"))
res.append(ok("🛢" not in m and "⚙️" not in m and "📌" not in m and "🔧" not in m, "декоративные эмодзи убраны (минимум)"))

# (4) мото-байк: gear НЕ показан (interval None)
mand_moto = [
    {"kind": "oil", "last": 30000, "interval": 5000},
    {"kind": "gear", "last": 0, "interval": None},           # мото → скрыт
    {"kind": "abs", "last": 0, "interval": 10000},
    {"kind": "airfilter", "last": 0, "interval": 20000},
]
m2 = S.msg_bike_card("NINJA 400 6334", "31000", mand_moto, {"state": "дома", "client": ""})
print("(4) мото — gear скрыт:")
res.append(ok("Редуктор" not in m2 and "น้ำมันเกียร์" not in m2, "gear НЕ показан на мото (не применимо)"))
res.append(ok("Масло — ✅ ещё <b>4000</b> км" in m2, "масло мото считается (30000+5000-31000=4000)"))
res.append(ok("ABS — ❗ <b>не делалось</b>" in m2 and "Возд. фильтр — ❗ <b>не делалось</b>" in m2, "abs/фильтр без записи → не делалось"))

# (5) TH-блок без кириллицы + тайские статусы
print("(5) TH без кириллицы:")
def th_block(s):
    out, inth = [], False
    for l in s.split("\n"):
        if l.lstrip().startswith("🇷🇺"): inth = False
        if l.lstrip().startswith("🇹🇭"): inth = True
        if inth: out.append(l)
    return "\n".join(out)
res.append(ok(not re.search(r"[А-Яа-яЁё]", th_block(m)), "в 🇹🇭-блоке нет кириллицы (двуязычность цела)"))
res.append(ok("เกินกำหนด" in m and "ยังไม่เคยทำ" in m and "───── เซอร์วิสตามกำหนด ─────" in m, "TH статусы/разделитель тайскими"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
